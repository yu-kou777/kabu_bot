import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import google.generativeai as genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime

# --- 設定 ---
GENAI_API_KEY = "gen-lang-client-0447054408"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 銘柄リスト（和名対応）
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

st.set_page_config(page_title="Jack株AI：最終兵器", layout="wide")

# --- RCI計算関数 ---
def calculate_rci(series, period=9):
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

# --- AI分析関数 ---
def get_ai_prediction(symbol, name, last_price, rsi, rci):
    prompt = f"銘柄:{name}({symbol}), 価格:{last_price:.0f}円, RSI:{rsi:.1f}, RCI:{rci:.1f}。変動要因、上昇期待日、目標株価を3行で回答して。"
    try:
        time.sleep(1)
        response = model.generate_content(prompt)
        return response.text
    except:
        return "AI分析制限中"

# --- メインスキャン処理 ---
def run_full_scan():
    results = []
    discord_summary = f"📢 **【Jack株AI 定刻スキャン報告】** ({datetime.now().strftime('%H:%M')})\n\n"
    
    for symbol, name in TICKER_MAP.items():
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty: continue
            
            # 条件：株価3000円以上 ＆ 出来高上位（直近5日平均）
            avg_vol = df['Volume'].tail(5).mean()
            last_p = df['Close'].iloc[-1]
            
            if last_p >= 3000 and avg_vol > 100000:
                df['RSI'] = ta.rsi(df['Close'], length=14)
                df['RCI'] = calculate_rci(df['Close'], period=9)
                
                rsi_val = df['RSI'].iloc[-1]
                rci_val = df['RCI'].iloc[-1]
                
                ai_text = get_ai_prediction(symbol, name, last_p, rsi_val, rci_val)
                
                data = {
                    "銘柄名": name, "コード": symbol, "株価": f"{last_p:,.0f}円",
                    "RSI": round(rsi_val, 1), "RCI": round(rci_val, 1), "AI予報": ai_text
                }
                results.append(data)
                discord_summary += f"🔹**{name}**({symbol}): {last_p:,.0f}円\n{ai_text}\n\n"
        except:
            continue
    
    # Discordに「ひとまとめ」で送信
    if results:
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=discord_summary[:2000]).execute()
    
    # 結果をCSV保存（Streamlitでの確認用）
    pd.DataFrame(results).to_csv("last_scan_result.csv", index=False)
    return results

# --- UI部 ---
st.title("🏆 Jack株AI：最終兵器ボード")

if st.button("🚀 今すぐ最新スキャンを実行"):
    with st.spinner("AI精査中..."):
        run_full_scan()
    st.success("スキャン完了！")

# 過去の結果を表示
try:
    history_df = pd.read_csv("last_scan_result.csv")
    st.subheader(f"📊 最新のスキャン結果")
    st.dataframe(history_df, use_container_width=True)
except:
    st.info("まだスキャンデータがありません。ボタンを押して開始してください。")

st.sidebar.info("💡 13:00と16:00に自動実行されます（GitHub Actions連動）")
