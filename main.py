import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import os
import time
from datetime import datetime, timedelta, timezone

# --- 設定 ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1472281747000393902/Fbclh0R3R55w6ZnzhenJ24coaUPKy42abh3uPO-fRjfQulk9OwAq-Cf8cJQOe2U4SFme"

# 📖 主要な和名データベース（ログの銘柄を網羅）
NAME_MAP = {
    "8035.T": "東京エレクトロン", "6920.T": "レーザーテック", "6857.T": "アドバンテスト",
    "6723.T": "ルネサス", "6758.T": "ソニーグループ", "6501.T": "日立製作所",
    "7203.T": "トヨタ自動車", "7267.T": "ホンダ", "7270.T": "SUBARU",
    "8306.T": "三菱UFJ", "9101.T": "日本郵船", "9104.T": "商船三井", "9107.T": "川崎汽船",
    "9984.T": "ソフトバンクG", "6330.T": "東洋エンジニアリング", "4385.T": "メルカリ",
    "4755.T": "楽天グループ", "6701.T": "日本電気", "5016.T": "ＪＸ金属", "7280.T": "ミツバ",
    "4901.T": "富士フイルム", "7049.T": "識学", "5406.T": "神戸製鋼所"
}

def load_targets():
    """JPX400のCSVがあれば優先、なければウォッチリストを読み込む"""
    targets = {}
    if os.path.exists('jpx400.csv'):
        df = pd.read_csv('jpx400.csv')
        targets = {f"{str(c).split('.')[0]}.T": n for c, n in zip(df['コード'], df['銘柄名'])}
    elif os.path.exists('list.xlsx'):
        df = pd.read_excel('list.xlsx')
        df.columns = [str(c).strip().lower() for c in df.columns]
        code_col = next((c for c in ['code', 'コード', '銘柄コード'] if c in df.columns), None)
        if code_col:
            for c in df[code_col]:
                code_str = f"{str(c).split('.')[0].strip()}.T"
                targets[code_str] = NAME_MAP.get(code_str, f"銘柄:{code_str}")
    if not targets:
        targets = {k: v for k, v in NAME_MAP.items()}
    return targets

def analyze_stock(ticker, name):
    try:
        # 高速化のため期間を3ヶ月に限定
        tkr = yf.Ticker(ticker)
        df = tkr.history(period="3mo", interval="1d")
        if len(df) < 25: return None
        
        # 指標計算（RSI, 25日乖離率, MACD需給）
        df['MA25'] = df['Close'].rolling(window=25).mean()
        df['Kairi'] = ((df['Close'] - df['MA25']) / df['MA25']) * 100
        df.ta.rsi(length=14, append=True)
        macd = ta.macd(df['Close'])
        df = pd.concat([df, macd], axis=1)
        
        price = int(df['Close'].iloc[-1])
        rsi = df['RSI_14'].iloc[-1]
        kairi = df['Kairi'].iloc[-1]
        macd_h = df['MACDh_12_26_9'].iloc[-1]
        
        # 需給判定
        jugyu = "📈 買い優勢" if macd_h > 0 else "📉 売り優勢" if macd_h < 0 else "☁️ 拮抗"

        # 判定条件（RSI 30以下、または70以上）
        if rsi <= 30 or kairi <= -10:
            status = "🐢✨ 買いサイン"
            comment = "📊⚡ 【RSI売られすぎ】反発の臨界点に到達！"
        elif rsi >= 70 or kairi >= 10:
            status = "🐇📉 売りサイン"
            comment = "⚠️ 【RSI買われすぎ】利確・調整の警戒ゾーンです。"
        else:
            return None

        return {
            "name": name, "code": ticker, "price": f"{price:,}",
            "rsi": round(rsi, 1), "jugyu": jugyu, "status": status, "comment": comment
        }
    except: return None

def send_discord(data):
    # 画像に基づいたAI監視レポート形式
    content = (
        f"🦅 **AI監視レポート**\n"
        f"{data['status']} **{data['name']}({data['code']})**\n"
        f"(RSI: {data['rsi']})\n"
        f"└ 価格: {data['price']}円 / 需給: {data['jugyu']}\n"
        f"📢 {data['comment']}"
    )
    payload = {"username": "株監視AI教授", "content": content}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

if __name__ == "__main__":
    jst = timezone(timedelta(hours=9))
    print(f"🚀 広域哨戒ミッション開始: {datetime.now(jst).strftime('%H:%M')}")
    targets = load_targets()
    for ticker, name in targets.items():
        res = analyze_stock(ticker, name)
        if res:
            send_discord(res)
            time.sleep(1) # Discordのレート制限対策
