import streamlit as st
import yfinance as yf
import pandas as pd
from google import genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os

# --- 設定（ジャックさんの最新キー） ---
GENAI_API_KEY = "AIzaSyAZZwHZrGLMhqWx1BEUwkGAkjC9DLylu5k"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

client = genai.Client(api_key=GENAI_API_KEY)

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

# テクニカル自作ロジック（許可なく変更しません）
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_rci(series, period=9):
    if len(series) < period: return np.zeros(len(series))
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

def get_ai_prediction_safe(symbol, name, last_p, rsi, rci):
    # テクニカル重視のプロンプト
    prompt = f"銘柄:{name}({symbol}), 価格:{last_p:.0f}円, RSI:{rsi:.1f}, RCI:{rci:.1f}。テクニカル視点から変動要因、上昇期待日、目標株価を3行で回答して。"
    for attempt in range(3):
        try:
            # 無料枠は1分に数回が限界。1銘柄ごとに15秒待って確実に答えを貰います。
            time.sleep(15)
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            if response.text:
                return response.text
        except Exception as e:
            time.sleep(20)
    return "分析リミット超過（後ほど再試行）"

def run_full_scan():
    print(f"🚀 スキャン開始...")
    results = []
    summary_items = []
    for symbol, name in TICKER_MAP.items():
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty: continue
            
            # テクニカル計算（ジャックさんの投資スタイルに直結）
            df['RSI'] = calculate_rsi(df['Close'], 14)
            df['RCI'] = calculate_rci(df['Close'], 9)
            last = df.iloc[-1]
            
            ai_text = get_ai_prediction_safe(symbol, name, last['Close'], last['RSI'], last['RCI'])
            
            results.append({"銘柄名": name, "コード": symbol, "現在値": f"{last['Close']:,.0f}円",
                            "RSI": round(last['RSI'], 1), "RCI": round(last['RCI'], 1), "AI予報": ai_text})
            summary_items.append(f"🔹**{name}**({symbol}): {last['Close']:,.0f}円\n{ai_text}")
            print(f"✅ {name} 精査完了")
        except Exception as e:
            print(f"Error {symbol}: {e}")
            continue
    
    if summary_items:
        msg = f"📢 **【Jack株AI 定刻報告】** ({datetime.now().strftime('%H:%M')})\n\n" + "\n\n".join(summary_items)
        # Discord文字数制限対策
        for i in range(0, len(msg), 1900):
            DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg[i:i+1900]).execute()
    
    pd.DataFrame(results).to_csv("last_scan_result.csv", index=False)
    print("✅ 全銘柄のAI精査を終了しました。")

# --- 実行分岐 ---
if "STREAMLIT_SERVER_PORT" in os.environ or "STREAMLIT_RUN_COMMAND" in os.environ:
    st.title("🏆 Jack株AI：最終兵器ボード")
    if st.button("🚀 最新AIスキャンを手動実行"):
        with st.spinner("AIが1銘柄ずつ丁寧にチャートを読み解いています... (約6分)"):
            run_full_scan()
        st.rerun()
    if os.path.exists("last_scan_result.csv"):
        st.dataframe(pd.read_csv("last_scan_result.csv"), use_container_width=True)
else:
    # GitHub Actions（背景）で実行された場合
    run_full_scan()
