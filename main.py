import yfinance as yf
import pandas as pd
import requests
import os

DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

TAKE_PROFIT = 1.13
STOP_LOSS = 0.95

base_tickers = {
    "トヨタ": "7203.T",
    "ソニーG": "6758.T",
    "キーエンス": "6861.T",
    "東京エレクトロン": "8035.T",
    "信越化学": "4063.T",
    "三菱UFJ": "8306.T",
    "三井住友FG": "8316.T",
    "みずほFG": "8411.T",
    "日立": "6501.T",
    "三菱重工": "7011.T",
    "任天堂": "7974.T",
    "リクルート": "6098.T",
    "ファーストリテイリング": "9983.T",
    "KDDI": "9433.T",
    "NTT": "9432.T",
    "ソフトバンクG": "9984.T",
    "HOYA": "7741.T",
    "デンソー": "6902.T",
    "村田製作所": "6981.T",
    "日本製鉄": "5401.T",
    "コマツ": "6301.T",
    "ダイキン": "6367.T",
    "ファナック": "6954.T",
    "富士通": "6702.T",
    "三菱商事": "8058.T",
    "三井物産": "8031.T",
    "伊藤忠": "8001.T",
    "丸紅": "8002.T",
    "日本郵船": "9101.T",
    "商船三井": "9104.T",
    "川崎汽船": "9107.T",
}

# ===== Yahoo売買代金ランキング取得 =====
ranking_url = "https://finance.yahoo.co.jp/stocks/ranking/tradingValueHigh?market=all"
ranking_tickers = {}

try:
    tables = pd.read_html(ranking_url)
    ranking_df = tables[0]

    codes = []
    for col in ranking_df.columns:
        if "名称・コード" in str(col) or "コード" in str(col):
            extracted = ranking_df[col].astype(str).str.extract(r"([0-9]{4}|[0-9]{3}[A-Z])")[0]
            codes.extend(extracted.dropna().tolist())

    codes = list(dict.fromkeys(codes))

    exclude_codes = {
        "1570", "1357", "1458", "1360", "1579", "1306", "1321", "1459"
    }

    for code in codes:
        if code not in exclude_codes:
            ranking_tickers[f"YAHOO_{code}"] = f"{code}.T"

except Exception as e:
    print("Yahooランキング取得エラー:", e)

all_tickers = {**base_tickers, **ranking_tickers}

print("固定銘柄数:", len(base_tickers))
print("ランキング銘柄数:", len(ranking_tickers))
print("合計チェック銘柄数:", len(all_tickers))

# ===== 日経地合いチェック =====
nikkei = yf.download("^N225", period="300d", interval="1d", auto_adjust=True, progress=False)

if isinstance(nikkei.columns, pd.MultiIndex):
    nikkei.columns = nikkei.columns.get_level_values(0)

nikkei["MA25"] = nikkei["Close"].rolling(25).mean()
nikkei["MA200"] = nikkei["Close"].rolling(200).mean()

latest = nikkei.iloc[-1]
prev = nikkei.iloc[-2]

nikkei_close = float(latest["Close"])
nikkei_ma25 = float(latest["MA25"])
nikkei_ma200 = float(latest["MA200"])
nikkei_ma200_prev = float(prev["MA200"])

market_on = (
    nikkei_close > nikkei_ma25 and
    nikkei_close > nikkei_ma200 and
    nikkei_ma200 > nikkei_ma200_prev
)

print("\n日経平均:", round(nikkei_close, 1))
print("日経25日線:", round(nikkei_ma25, 1))
print("日経200日線:", round(nikkei_ma200, 1))
print("地合い:", "ON" if market_on else "OFF")

if not market_on:
    print("\n地合いNG → 今日は新規買いなし")

else:
    results = []

    for name, ticker in all_tickers.items():
        try:
            data = yf.download(ticker, period="120d", interval="1d", auto_adjust=True, progress=False)

            if len(data) < 35:
                continue

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            data["MA25"] = data["Close"].rolling(25).mean()
            data["VolumeAvg5"] = data["Volume"].rolling(5).mean()
            data["Volatility20"] = data["Close"].pct_change().rolling(20).std()

            latest = data.iloc[-1]

            close = float(latest["Close"])
            ma25 = float(latest["MA25"])
            volume = float(latest["Volume"])
            volume_avg5 = float(latest["VolumeAvg5"])
            volatility = float(latest["Volatility20"])

            high10_prev = float(data["High"].iloc[-11:-1].max())
            change_1d = float(data["Close"].pct_change().iloc[-1])

            # ===== 戦略フィルター =====
            if volatility < 0.010:
                continue

            # 全銘柄：前日比+10%以上は除外
            if change_1d > 0.10:
                continue

            # ランキング銘柄：前日比+8%以上は除外
            if name.startswith("YAHOO_") and change_1d > 0.08:
                continue

            if close > ma25 and close > high10_prev and volume > volume_avg5:
                results.append({
                    "銘柄": name,
                    "コード": ticker,
                    "現在値": round(close, 1),
                    "25日線": round(ma25, 1),
                    "10日高値": round(high10_prev, 1),
                    "出来高倍率": round(volume / volume_avg5, 2),
                    "ボラ": round(volatility, 4),
                    "前日比%": round(change_1d * 100, 2),
                    "損切-5%": round(close * STOP_LOSS, 1),
                    "利確+13%": round(close * TAKE_PROFIT, 1),
                    "区分": "ランキング" if name.startswith("YAHOO_") else "固定"
                })

        except Exception as e:
            print("取得エラー:", name, ticker, e)

    df = pd.DataFrame(results)

    if df.empty:
        print("\n本日の候補なし")

        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": "【本日の買い候補】\n本日の候補なし"
        })

    else:
        df = df.drop_duplicates(subset=["コード"])
        df = df.sort_values("出来高倍率", ascending=False)

        fixed_df = df[df["区分"] == "固定"]
        ranking_df = df[df["区分"] == "ランキング"]

        selected = pd.concat([
            fixed_df.head(2),
            ranking_df.head(1)
        ])

        if len(selected) < 3:
            remaining = df[~df["コード"].isin(selected["コード"])]
            selected = pd.concat([selected, remaining.head(3 - len(selected))])

        selected = selected.drop_duplicates(subset=["コード"]).head(3)

        print("\n本日の買い候補 上位10")
        display(df.head(10))

        print("\n自動選定 3銘柄")
        display(selected)

        msg = "【本日の買い候補】\n"

        for _, row in selected.iterrows():
            msg += f"\n{row['銘柄']} ({row['コード']})"
            msg += f"\n現在値: {row['現在値']}"
            msg += f"\n損切: {row['損切-5%']}"
            msg += f"\n利確: {row['利確+13%']}"
            msg += f"\n区分: {row['区分']}\n"

        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
