import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os

# --- 設定（ジャックさんの最新キー） ---
GENAI_API_KEY = "AIzaSyAZZwHZrGLMhqWx1BEUwkGAkjC9DLylu5k"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 銘柄リスト
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

def calculate_rsi(series, period=14):
    """RSIを独自計算"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_rci(series, period=9):
    """RCIを独自計算"""
    if len(series) < period: return np.zeros(len(series))
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

def get_ai_prediction_safe(symbol, name, last_price, rsi, rci):
    prompt = f"銘柄:{name}({symbol}), 価格:{last_price:.0f}円, RSI:{rsi:.1f}, RCI:{rci:.1f}。変動要因、上昇期待日、目標株価を3行で鋭く回答して。"
    for attempt in range(3):
        try:
            time.sleep(12) 
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except:
            time.sleep(20)
    return "分析制限中"

def run_full_scan():
    results = []
    summary_items = []
    for symbol, name in TICKER_MAP.items():
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty: continue
            
            # テクニカル指標を自作関数で計算
            df['RSI'] = calculate_rsi(df['Close'], 14)
            df['RCI'] = calculate_rci(df['Close'], 9)
            last = df.iloc[-1]
            
            ai_text = get_ai_prediction_safe(symbol, name, last['Close'], last['RSI'], last['RCI'])
            
            data = {
                "銘柄名": name, "コード": symbol, "現在値": f"{last['Close']:,.0f}円",
                "RSI": round(last['RSI'], 1) if not np.isnan(last['RSI']) else 0, 
                "RCI": round(last['RCI'], 1) if not np.isnan(last['RCI']) else 0, 
                "AI予報": ai_text
            }
            results.append(data)
            summary_items.append(f"🔹**{name}**({symbol}): {last['Close']:,.0f}円\n{ai_text}")
        except:
            continue
    
    if summary_items:
        full_msg = f"📢 **【Jack株AI 定刻スキャン報告】** ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n" + "\n\n".join(summary_items)
        for i in range(0, len(full_msg), 1900):
            DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=full_msg[i:i+1900]).execute()
            
    pd.DataFrame(results).to_csv("last_scan_result.csv", index=False)
    return results

st.title("🏆 Jack株AI：最終兵器ダッシュボード")

if st.button("🚀 今すぐ最新スキャンを実行"):
    with st.spinner("AI精査中... (約5分かかります)"):
        run_full_scan()
    st.rerun()

if os.path.exists("last_scan_result.csv"):
    df_history = pd.read_csv("last_scan_result.csv")
    st.subheader("📊 最新のスキャン結果")
    st.dataframe(df_history, use_container_width=True)
