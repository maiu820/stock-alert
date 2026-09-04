import yfinance as yf
import pandas as pd
import requests
import os
import datetime

# =========================
# Discord設定
# =========================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

if not DISCORD_WEBHOOK_URL:
    raise ValueError("DISCORD_WEBHOOK_URL が設定されていません")

# =========================
# 基本設定
# =========================
TAKE_PROFIT = 1.13
STOP_LOSS = 0.95
MAX_BUY_AMOUNT = 500000  # 100株で50万円以内

portfolio_file = "portfolio.csv"

# =========================
# 固定銘柄
# =========================
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

# =========================
# Discord送信関数
# =========================
def send_discord(msg):
    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": msg},
            timeout=15
        )

        if response.status_code not in [200, 204]:
            print("Discord送信エラー:", response.status_code, response.text)

    except Exception as e:
        print("Discord送信例外:", e)


# =========================
# 売りシグナル
# =========================
sell_msgs = []

if os.path.exists(portfolio_file):

    try:
        pf = pd.read_csv(portfolio_file)

        for _, row in pf.iterrows():

            ticker = row["コード"]
            buy_price = float(row["購入価格"])
            buy_date = pd.to_datetime(row["購入日"])

            try:
                data = yf.download(
                    ticker,
                    period="10d",
                    interval="1d",
                    auto_adjust=True,
                    progress=False
                )

                if len(data) == 0:
                    continue

                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)

                current_price = float(data["Close"].iloc[-1])

                change = current_price / buy_price

                days_held = (
                    datetime.datetime.now() - buy_date
                ).days

                if change >= TAKE_PROFIT:
                    sell_msgs.append(
                        f"利確: {ticker} 現在値 {round(current_price,1)}"
                    )

                elif change <= STOP_LOSS:
                    sell_msgs.append(
                        f"損切: {ticker} 現在値 {round(current_price,1)}"
                    )

                elif days_held >= 5:
                    sell_msgs.append(
                        f"5日経過: {ticker} 現在値 {round(current_price,1)}"
                    )

            except Exception as e:
                print("売りチェックエラー:", ticker, e)

    except Exception as e:
        print("portfolio.csv読み込みエラー:", e)


# =========================
# Yahoo売買代金ランキング
# =========================
ranking_url = "https://finance.yahoo.co.jp/stocks/ranking/tradingValueHigh?market=all"

ranking_tickers = {}

try:
    tables = pd.read_html(ranking_url)

    ranking_df = tables[0]

    codes = []

    for col in ranking_df.columns:

        if "名称・コード" in str(col) or "コード" in str(col):

            extracted = (
                ranking_df[col]
                .astype(str)
                .str.extract(r"([0-9]{4}|[0-9]{3}[A-Z])")[0]
            )

            codes.extend(
                extracted.dropna().tolist()
            )

    codes = list(dict.fromkeys(codes))

    exclude_codes = {
        "1570",
        "1357",
        "1458",
        "1360",
        "1579",
        "1306",
        "1321",
        "1459"
    }

    for code in codes:

        if code not in exclude_codes:

            ranking_tickers[
                f"YAHOO_{code}"
            ] = f"{code}.T"

except Exception as e:
    print("Yahooランキング取得エラー:", e)


all_tickers = {
    **base_tickers,
    **ranking_tickers
}

print("固定銘柄数:", len(base_tickers))
print("ランキング銘柄数:", len(ranking_tickers))
print("合計チェック銘柄数:", len(all_tickers))


# =========================
# 日経地合い判定
# =========================
nikkei = yf.download(
    "^N225",
    period="300d",
    interval="1d",
    auto_adjust=True,
    progress=False
)

if isinstance(nikkei.columns, pd.MultiIndex):
    nikkei.columns = nikkei.columns.get_level_values(0)

nikkei["MA25"] = nikkei["Close"].rolling(25).mean()
nikkei["MA200"] = nikkei["Close"].rolling(200).mean()

latest_nikkei = nikkei.iloc[-1]

nikkei_close = float(latest_nikkei["Close"])
nikkei_ma25 = float(latest_nikkei["MA25"])
nikkei_ma200 = float(latest_nikkei["MA200"])

nikkei_ma200_20days_ago = float(
    nikkei["MA200"].iloc[-21]
)

# =========================
# 相場モード
# =========================
if (
    nikkei_close > nikkei_ma25
    and nikkei_close > nikkei_ma200
    and nikkei_ma200 > nikkei_ma200_20days_ago
):

    market_mode = "NORMAL"

elif (
    nikkei_close < nikkei_ma25
    and nikkei_close > nikkei_ma200
    and nikkei_ma200 > nikkei_ma200_20days_ago
):

    market_mode = "PULLBACK"

else:

    market_mode = "OFF"


print("\n日経平均:", round(nikkei_close, 1))
print("日経25日線:", round(nikkei_ma25, 1))
print("日経200日線:", round(nikkei_ma200, 1))
print("相場モード:", market_mode)


# =========================
# NORMAL
# =========================
if market_mode == "NORMAL":

    results = []
    watch_results = []

    for name, ticker in all_tickers.items():

        try:

            data = yf.download(
                ticker,
                period="300d",
                interval="1d",
                auto_adjust=True,
                progress=False
            )

            if len(data) < 220:
                continue

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            data["MA25"] = (
                data["Close"]
                .rolling(25)
                .mean()
            )

            data["VolumeAvg5"] = (
                data["Volume"]
                .rolling(5)
                .mean()
            )

            data["Volatility20"] = (
                data["Close"]
                .pct_change(fill_method=None)
                .rolling(20)
                .std()
            )

            latest = data.iloc[-1]

            close = float(latest["Close"])

            buy_amount = close * 100

            if buy_amount > MAX_BUY_AMOUNT:
                continue

            ma25 = float(latest["MA25"])
            volume = float(latest["Volume"])
            volume_avg5 = float(latest["VolumeAvg5"])
            volatility = float(latest["Volatility20"])

            high10_prev = float(
                data["High"]
                .iloc[-11:-1]
                .max()
            )

            change_1d = float(
                data["Close"]
                .pct_change(fill_method=None)
                .iloc[-1]
            )

            # 急騰しすぎ排除
            if change_1d > 0.08:
                continue

            item = {
                "銘柄": name,
                "コード": ticker,
                "現在値": round(close, 1),
                "概算購入額": round(buy_amount, 0),
                "25日線": round(ma25, 1),
                "10日高値": round(high10_prev, 1),
                "出来高倍率": round(volume / volume_avg5, 2),
                "ボラ": round(volatility, 4),
                "前日比%": round(change_1d * 100, 2),
                "損切-5%": round(close * STOP_LOSS, 1),
                "利確+13%": round(close * TAKE_PROFIT, 1),
                "区分":
                    "ランキング"
                    if name.startswith("YAHOO_")
                    else "固定"
            }

            # =========================
            # 本命条件
            # =========================
            if (
                close > ma25
                and close > high10_prev * 0.97
                and volume > volume_avg5 * 1.05
                and volatility >= 0.009
            ):

                results.append(item)

            # =========================
            # 準本命
            # =========================
            elif (
                close > ma25
                and close > high10_prev * 0.98
                and volume > volume_avg5
                and volatility >= 0.008
            ):

                watch_results.append(item)

            # =========================
            # 弱め監視
            # =========================
            elif (
                close > ma25
                and volume > volume_avg5
                and volatility >= 0.007
            ):

                watch_results.append(item)

        except Exception as e:
            print(
                "取得エラー:",
                name,
                ticker,
                e
            )


    df = pd.DataFrame(results)

    watch_df = pd.DataFrame(
        watch_results
    )


    # =========================
    # 本命あり
    # =========================
    if not df.empty:

        df = (
            df
            .drop_duplicates(
                subset=["コード"]
            )
            .sort_values(
                "出来高倍率",
                ascending=False
            )
        )

        fixed_df = df[
            df["区分"] == "固定"
        ]

        ranking_df = df[
            df["区分"] == "ランキング"
        ]

        selected = pd.concat([
            fixed_df.head(2),
            ranking_df.head(1)
        ])

        if len(selected) < 3:

            remaining = df[
                ~df["コード"]
                .isin(selected["コード"])
            ]

            selected = pd.concat([
                selected,
                remaining.head(
                    3 - len(selected)
                )
            ])

        selected = (
            selected
            .drop_duplicates(
                subset=["コード"]
            )
            .head(3)
        )

        msg = (
            "【本日の買い候補】\n"
            "相場モード: NORMAL\n"
        )

        for _, row in selected.iterrows():

            msg += (
                f"\n{row['銘柄']} "
                f"({row['コード']})"
            )

            msg += (
                f"\n現在値: "
                f"{row['現在値']}"
            )

            msg += (
                f"\n概算購入額: "
                f"{row['概算購入額']}円"
            )

            msg += (
                f"\n損切: "
                f"{row['損切-5%']}"
            )

            msg += (
                f"\n利確: "
                f"{row['利確+13%']}"
            )

            msg += (
                f"\n出来高倍率: "
                f"{row['出来高倍率']}"
            )

            msg += (
                f"\n前日比: "
                f"{row['前日比%']}%"
            )

            msg += (
                f"\n区分: "
                f"{row['区分']}\n"
            )

        send_discord(msg)


    # =========================
    # 本命なし
    # =========================
    else:

        if watch_df.empty:

            msg = (
                "【本日の買い候補】\n"
                "相場モード: NORMAL\n"
                "本命候補なし\n"
                "監視候補もなし"
            )

            send_discord(msg)

        else:

            watch_df = (
                watch_df
                .drop_duplicates(
                    subset=["コード"]
                )
                .sort_values(
                    "出来高倍率",
                    ascending=False
                )
            )

            msg = (
                "【本日の買い候補】\n"
                "相場モード: NORMAL\n"
                "本命候補なし\n\n"
                "【監視候補】"
                "※買わない。見るだけ\n"
            )

            for _, row in (
                watch_df.head(5)
                .iterrows()
            ):

                msg += (
                    f"\n{row['銘柄']} "
                    f"({row['コード']})"
                )

                msg += (
                    f"\n現在値: "
                    f"{row['現在値']}"
                )

                msg += (
                    f"\n概算購入額: "
                    f"{row['概算購入額']}円"
                )

                msg += (
                    f"\n出来高倍率: "
                    f"{row['出来高倍率']}"
                )

                msg += (
                    f"\nボラ: "
                    f"{row['ボラ']}"
                )

                msg += (
                    f"\n前日比: "
                    f"{row['前日比%']}%\n"
                )

            send_discord(msg)


# =========================
# PULLBACK
# =========================
elif market_mode == "PULLBACK":

    dip_results = []
    near_results = []

    for name, ticker in base_tickers.items():

        try:

            data = yf.download(
                ticker,
                period="300d",
                interval="1d",
                auto_adjust=True,
                progress=False
            )

            if len(data) < 220:
                continue

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            data["MA25"] = (
                data["Close"]
                .rolling(25)
                .mean()
            )

            data["MA200"] = (
                data["Close"]
                .rolling(200)
                .mean()
            )

            # RSI14
            delta = data["Close"].diff()

            gain = (
                delta.clip(lower=0)
                .rolling(14)
                .mean()
            )

            loss = (
                -delta.clip(upper=0)
                .rolling(14)
                .mean()
            )

            rs = gain / loss

            data["RSI14"] = (
                100
                - (
                    100
                    / (1 + rs)
                )
            )

            latest = data.iloc[-1]

            close = float(latest["Close"])
            buy_amount = close * 100

            # 100株50万円以内
            if buy_amount > MAX_BUY_AMOUNT:
                continue

            ma25 = float(latest["MA25"])
            ma200 = float(latest["MA200"])

            ma200_20days_ago = float(
                data["MA200"].iloc[-21]
            )

            rsi = float(latest["RSI14"])

            high20 = float(
                data["High"]
                .iloc[-21:-1]
                .max()
            )

            drawdown = (
                close / high20
            ) - 1

            change_1d = float(
                data["Close"]
                .pct_change(fill_method=None)
                .iloc[-1]
            )

            # =========================
            # 押し目条件
            # =========================
            dip_condition = (

                # 長期上昇
                close > ma200

                and ma200 > ma200_20days_ago

                # 短期調整
                and close < ma25

                # 20日高値から5〜15%下落
                and -0.15 <= drawdown <= -0.05

                # RSI 30〜50
                and 30 <= rsi <= 50

                # 1日暴落を除外
                and change_1d > -0.08
            )

            item = {

                "銘柄": name,

                "コード": ticker,

                "現在値": round(close, 1),

                "概算購入額": round(
                    buy_amount,
                    0
                ),

                "25日線": round(
                    ma25,
                    1
                ),

                "200日線": round(
                    ma200,
                    1
                ),

                "20日高値": round(
                    high20,
                    1
                ),

                "高値から下落%": round(
                    drawdown * 100,
                    2
                ),

                "RSI14": round(
                    rsi,
                    1
                ),

                "前日比%": round(
                    change_1d * 100,
                    2
                ),

                "損切-5%": round(
                    close * STOP_LOSS,
                    1
                ),

                "利確+13%": round(
                    close * TAKE_PROFIT,
                    1
                )
            }

            # =========================
            # 押し目候補
            # =========================
            if dip_condition:

                item["押し目スコア"] = 100
                dip_results.append(item)

            else:

                # =========================
                # 押し目に近い銘柄をスコア化
                # =========================
                score = 0

                # ① 200日線より上
                if close > ma200:
                    score += 25

                # ② 200日線が上向き
                if ma200 > ma200_20days_ago:
                    score += 25

                # ③ 25日線より下
                if close < ma25:
                    score += 15

                # ④ 高値からの下落率
                if -0.15 <= drawdown <= -0.05:
                    score += 20

                elif -0.18 <= drawdown < -0.15:
                    score += 10

                elif -0.05 < drawdown <= -0.03:
                    score += 10

                # ⑤ RSI
                if 30 <= rsi <= 50:
                    score += 15

                elif 25 <= rsi < 30:
                    score += 8

                elif 50 < rsi <= 55:
                    score += 8

                # 暴落日は減点
                if change_1d <= -0.08:
                    score -= 20

                item["押し目スコア"] = score

                near_results.append(item)

        except Exception as e:

            print(
                "押し目取得エラー:",
                name,
                ticker,
                e
            )


    dip_df = pd.DataFrame(
        dip_results
    )

    near_df = pd.DataFrame(
        near_results
    )


    # =========================
    # 押し目候補あり
    # =========================
    if not dip_df.empty:

        dip_df = (
            dip_df
            .sort_values(
                "高値から下落%",
                ascending=True
            )
            .head(5)
        )

        msg = (
            "【押し目買い候補】\n"
            "⚠️ 相場モード: PULLBACK\n"
            "長期上昇トレンド内の短期調整候補\n"
        )

        for _, row in dip_df.iterrows():

            msg += (
                f"\n{row['銘柄']} "
                f"({row['コード']})"
            )

            msg += (
                f"\n現在値: "
                f"{row['現在値']}"
            )

            msg += (
                f"\n概算購入額: "
                f"{row['概算購入額']}円"
            )

            msg += (
                f"\n25日線: "
                f"{row['25日線']}"
            )

            msg += (
                f"\n200日線: "
                f"{row['200日線']}"
            )

            msg += (
                f"\n20日高値から: "
                f"{row['高値から下落%']}%"
            )

            msg += (
                f"\nRSI14: "
                f"{row['RSI14']}"
            )

            msg += (
                f"\n前日比: "
                f"{row['前日比%']}%"
            )

            msg += (
                f"\n損切目安: "
                f"{row['損切-5%']}"
            )

            msg += (
                f"\n利確目安: "
                f"{row['利確+13%']}\n"
            )


        # =========================
        # 押し目に近い上位3銘柄
        # =========================
        if not near_df.empty:

            near_df = (
                near_df
                .sort_values(
                    "押し目スコア",
                    ascending=False
                )
                .head(3)
            )

            msg += (
                "\n\n【押し目監視 上位3】"
                "\n※まだ買い条件未達\n"
            )

            for _, row in near_df.iterrows():

                msg += (
                    f"\n{row['銘柄']} "
                    f"({row['コード']})"
                )

                msg += (
                    f"\n押し目スコア: "
                    f"{row['押し目スコア']}点"
                )

                msg += (
                    f"\n現在値: "
                    f"{row['現在値']}"
                )

                msg += (
                    f"\n20日高値から: "
                    f"{row['高値から下落%']}%"
                )

                msg += (
                    f"\nRSI14: "
                    f"{row['RSI14']}"
                )

                msg += (
                    f"\n前日比: "
                    f"{row['前日比%']}%\n"
                )

        send_discord(msg)


    # =========================
    # 押し目候補なし
    # =========================
    else:

        msg = (
            "【押し目買いチェック】\n"
            "相場モード: PULLBACK\n\n"
            "現在は地合い調整中\n"
            "押し目条件に該当する固定銘柄なし\n"
        )


        # =========================
        # 近い銘柄 上位3
        # =========================
        if not near_df.empty:

            near_df = (
                near_df
                .sort_values(
                    "押し目スコア",
                    ascending=False
                )
                .head(3)
            )

            msg += (
                "\n【押し目監視 上位3】"
                "\n※まだ買い条件未達\n"
            )

            for _, row in near_df.iterrows():

                msg += (
                    f"\n{row['銘柄']} "
                    f"({row['コード']})"
                )

                msg += (
                    f"\n押し目スコア: "
                    f"{row['押し目スコア']}点"
                )

                msg += (
                    f"\n現在値: "
                    f"{row['現在値']}"
                )

                msg += (
                    f"\n20日高値から: "
                    f"{row['高値から下落%']}%"
                )

                msg += (
                    f"\nRSI14: "
                    f"{row['RSI14']}"
                )

                msg += (
                    f"\n前日比: "
                    f"{row['前日比%']}%\n"
                )

        send_discord(msg)
