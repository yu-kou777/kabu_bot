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

st.set_page_config(page_title="Jack株AI：最終兵器", layout="wide")

# --- RCI計算用関数 ---
def calculate_rci(series, period=9):
    """RCIを独自計算する関数"""
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        # 期間分のデータを取得
        data = series.iloc[i - period + 1 : i + 1]
        # 日付の順位 (新しい方が1)
        time_rank = np.arange(period, 0, -1)
        # 価格の順位 (高い方が1)
        price_rank = data.rank(ascending=False).values
        # 差の2乗の合計
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        # RCIの公式
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

# --- 銘柄リスト ---
TICKERS = [
    "8035.T", "9984.T", "6758.T", "7203.T", "6920.T", "6857.T", "6146.T", "4063.T",
    "8058.T", "8316.T", "9101.T", "7011.T", "4502.T", "6501.T", "6702.T", "6201.T",
    "9104.T", "6367.T", "6273.T", "7974.T", "9020.T", "2914.T", "4061.T", "6723.T"
]

def analyze_and_notify(symbol, df):
    last = df.iloc[-1]
    prompt = f"""
    銘柄コード:{symbol}, 価格:{last['Close']:.0f}円, RSI:{last['RSI']:.1f}, RCI:{last['RCI']:.1f}
    上記データから「変動要因」「上昇予想日」「目標株価」を3行で鋭く回答してください。
    """
    try:
        response = model.generate_content(prompt)
        ai_text = response.text
        msg = f"🚀 **【AI分析完了】{symbol}**\n現値: {last['Close']:,.0f}円\n{ai_text}"
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg).execute()
        return ai_text
    except:
        return "API待機中..."

# --- UI ---
st.title("🏆 Jack株AI：最終兵器ダッシュボード")

if st.button("🚀 フルスキャン ＆ 攻略本作成を開始"):
    results = []
    progress_bar = st.progress(0)
    status_area = st.empty()
    
    for i, symbol in enumerate(TICKERS):
        status_area.write(f"🔍 分析中 ({i+1}/{len(TICKERS)}): {symbol}")
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo") # RCI計算のため少し長めに取得
            
            if not df.empty:
                # RSIはpandas_taでOK
                df['RSI'] = ta.rsi(df['Close'], length=14)
                # RCIは独自関数で計算
                df['RCI'] = calculate_rci(df['Close'], period=9)
                
                if i % 5 == 0 and i > 0: time.sleep(10)
                
                ai_result = analyze_and_notify(symbol, df)
                
                results.append({
                    "銘柄": symbol,
                    "現在値": f"{df['Close'].iloc[-1]:,.0f}円",
                    "RSI": round(df['RSI'].iloc[-1], 1) if not pd.isna(df['RSI'].iloc[-1]) else 0,
                    "RCI": round(df['RCI'].iloc[-1], 1) if not pd.isna(df['RCI'].iloc[-1]) else 0,
                    "AI予報": ai_result
                })
            time.sleep(1)
        except Exception as e:
            st.error(f"{symbol} でエラー: {e}")
        progress_bar.progress((i + 1) / len(TICKERS))

    status_area.success("✅ 全銘柄の分析が完了しました！")
    st.dataframe(pd.DataFrame(results), use_container_width=True)
