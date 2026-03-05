import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import google.generativeai as genai
from discord_webhook import DiscordWebhook
import time
import numpy as np

# --- 設定 ---
GENAI_API_KEY = "gen-lang-client-0447054408"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="Jack株AI：真・最終兵器", layout="wide")

# --- RCI計算 ---
def calculate_rci(series, period=9):
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

# --- AI分析関数 (リトライロジック付) ---
def analyze_with_retry(symbol, df):
    last = df.iloc[-1]
    prompt = f"銘柄:{symbol}, 価格:{last['Close']:.0f}円, RSI:{last['RSI']:.1f}, RCI:{last['RCI']:.1f}。変動要因、上昇期待日、目標株価を3行で回答して。"
    
    for _ in range(3): # 3回までリトライ
        try:
            time.sleep(2) # 1リクエストごとに2秒待機
            response = model.generate_content(prompt)
            return response.text
        except:
            time.sleep(10) # 制限時は10秒待機
    return "APIリミット超過。後ほど手動で確認してください。"

# --- UI ---
st.title("🏆 Jack株AI：プライム市場全件精査モード")

# スキャン条件設定
col_a, col_b = st.columns(2)
with col_a:
    min_price = st.number_input("株価下限 (円)", value=3000)
with col_b:
    min_volume = st.number_input("5日平均出来高下限 (株)", value=100000)

# 実行ボタン
if st.button("🚀 プライム市場の出来高上位銘柄をAIスキャン"):
    # 本来は全件リストが必要ですが、ここでは主要200社をベースに動かします
    # ※全3,800銘柄をyfinanceで叩くと数時間かかるため、活況銘柄を中心に構成
    TICKERS_LARGE = ["8035.T", "9984.T", "6758.T", "7203.T", "6920.T", "6857.T", "6146.T", "4063.T", "8058.T", "8316.T", "9101.T", "7011.T", "4502.T", "6501.T", "6702.T", "6201.T", "9104.T", "6367.T", "6273.T", "7974.T", "9020.T", "2914.T", "4061.T", "6723.T", "4503.T", "6098.T", "6902.T", "6981.T", "7741.T", "8001.T"] # ここにさらに追加可能
    
    results = []
    progress_bar = st.progress(0)
    status = st.empty()

    for i, symbol in enumerate(TICKERS_LARGE):
        status.write(f"🔍 スキャン中 ({i+1}/{len(TICKERS_LARGE)}): {symbol}")
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            
            if df.empty: continue
            
            # 条件判定: 株価 & 5日平均出来高
            avg_vol = df['Volume'].tail(5).mean()
            last_price = df['Close'].iloc[-1]
            
            if last_price >= min_price and avg_vol >= min_volume:
                df['RSI'] = ta.rsi(df['Close'], length=14)
                df['RCI'] = calculate_rci(df['Close'], period=9)
                
                # AI分析を実行
                ai_text = analyze_with_retry(symbol, df)
                
                res_data = {
                    "銘柄": symbol,
                    "現在値": f"{last_price:,.0f}円",
                    "5日平均出来高": f"{avg_vol/10000:.1f}万株",
                    "RSI": round(df['RSI'].iloc[-1], 1),
                    "RCI": round(df['RCI'].iloc[-1], 1),
                    "AI予報": ai_text
                }
                results.append(res_data)
                
                # Discord通知
                DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=f"💎 **{symbol}** 一致！\n{ai_text}").execute()
            
        except Exception as e:
            print(f"Error {symbol}: {e}")
        
        progress_bar.progress((i + 1) / len(TICKERS_LARGE))

    status.success(f"✅ スキャン完了！ 条件合致: {len(results)}件")
    st.dataframe(pd.DataFrame(results), use_container_width=True)
