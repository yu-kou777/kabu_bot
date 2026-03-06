import yfinance as yf
import pandas as pd
from google import genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os

# --- 設定 ---
# GitHubのSecretsに登録した名前と一致させてください
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY") 
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 万が一URLがNoneだった場合の安全装置
if not DISCORD_WEBHOOK_URL:
    print("⚠️ Discord Webhook URLが設定されていません。環境変数を確認してください。")
    # ここに直接URLを書き込むことも可能ですが、Secretsを推奨します
    # DISCORD_WEBHOOK_URL = "https://discord.com/..."

client = genai.Client(api_key=GENAI_API_KEY)

# 監視銘柄（ジャックさんの主力24銘柄）
TICKER_MAP = {
    "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6758.T": "ソニーG",
    "7203.T": "トヨタ自動車", "6920.T": "レーザーテック", "6857.T": "アドバンテスト",
    "6146.T": "ディスコ", "4063.T": "信越化学", "8058.T": "三菱商事",
    "8316.T": "三井住友FG", "9101.T": "日本郵船", "7011.T": "三菱重工",
    "4502.T": "武田薬品", "6501.T": "日立製作所", "6702.T": "富士通",
    "6201.T": "豊田自動織機", "9104.T": "商船三井", "6367.T": "ダイキン工業",
    "6273.T": "SMC", "7974.T": "任天堂", "9020.T": "JR東日本",
    "2914.T": "JT", "4061.T": "デンカ", "6723.T": "ルネサス"
}

# --- テクニカル計算ロジック ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_rci(series, period=9):
    """
    RCI (Rank Correlation Index) 計算
    公式: $$RCI = (1 - \\frac{6 \sum d^2}{n(n^2 - 1)}) \times 100$$
    """
    if len(series) < period: return np.zeros(len(series))
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

def run_full_scan():
    print("🚀 ジャック株AI：スキャン開始...")
    scan_details = ""
    hit_count = 0
    
    for symbol, name in TICKER_MAP.items():
        try:
            print(f"📡 取得中: {name}")
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty: continue
            
            rsi = round(calculate_rsi(df['Close'], 14).iloc[-1], 1)
            rci = round(calculate_rci(df['Close'], 9)[-1], 1)
            price = f"{df['Close'].iloc[-1]:,.0f}"
            
            # --- ジャックさん専用：緊急アラート判定 ---
            alert = ""
            if rsi < 21 and rci < -79:
                alert = "🔥【超絶売られすぎ・反発期待】"
            elif rsi > 89 and rci > 94:
                alert = "⚠️【超過熱・高値警戒】"
            
            print(f"  -> RSI:{rsi} / RCI:{rci} {alert}")
            scan_details += f"{alert}{name}({symbol}): RSI:{rsi}, RCI:{rci}, 価格:{price}円\n"
            hit_count += 1
        except Exception as e:
            print(f"  ❌ {name} エラー: {e}")
            continue

    if not scan_details:
        print("❌ 解析対象のデータが取得できませんでした。")
        return

    # 🤖 AI一括分析（429エラー回避のため、1回のリクエストにまとめます）
    print("🤖 AIが攻略本を執筆中...")
    prompt = f"""
    あなたは凄腕のテクニカルトレーダーです。以下の銘柄（特に🔥や⚠️）を分析し、
    「変動要因」「上昇期待日」「目標株価」を銘柄ごとに3行で簡潔に回答してください。
    【対象データ】
    {scan_details}
    """
    
    try:
        # 無料枠の制限を考慮し、15秒待機してからリクエスト
        time.sleep(15)
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        ai_analysis = response.text
    except Exception as e:
        ai_analysis = f"AI分析エラー: {str(e)}"

    # 📢 Discord送信（URLエラー対策済み）
    if DISCORD_WEBHOOK_URL:
        now_str = datetime.now().strftime('%m/%d %H:%M')
        msg = f"📢 **【Jack株AI 定刻報告】** ({now_str})\n\n{ai_analysis}"
        try:
            # 2000文字制限対策
            for i in range(0, len(msg), 1900):
                DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg[i:i+1900]).execute()
            print("✅ Discordへの送信が完了しました。")
        except Exception as e:
            print(f"❌ Discord送信失敗: {e}")
    
    print("✅ すべての工程が完了しました。")

if __name__ == "__main__":
    import sys
    # 背景実行（GitHub Actions）か Streamlit かを判定
    if "streamlit" in sys.argv[0] or any("streamlit" in arg for arg in sys.argv):
        import streamlit as st
        st.title("🏆 Jack株AI：攻略本ダッシュボード")
        if st.button("🚀 最新スキャンを開始"):
            with st.spinner("AI精査中..."):
                run_full_scan()
                st.success("完了！ Discordを確認してください。")
    else:
        run_full_scan()
