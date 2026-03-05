import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import google.generativeai as genai
from discord_webhook import DiscordWebhook
import time
from concurrent.futures import ThreadPoolExecutor

# --- 設定（ジャックさんのキーを反映済み） ---
GENAI_API_KEY = "gen-lang-client-0447054408"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="Jack株AI：最終兵器", layout="wide")

def analyze_stock_ai(symbol, name, df):
    """Gemini AIを使って銘柄を深く分析し、Discordへも通知する"""
    last_price = df['Close'].iloc[-1]
    recent_data = df.tail(3)[['Close', 'Volume']].to_string()
    
    prompt = f"""
    銘柄: {name} ({symbol}) / 現在値: {last_price:.0f}円
    直近3日データ:
    {recent_data}

    プロの視点で以下3点を日本語で簡潔に回答してください。
    1. 変動要因（何に連動して動いているか）
    2. 上昇予想日（具体的な日程や条件）
    3. 目標株価（円単位の数値）
    """
    
    try:
        # 無料版API制限回避のための微調整
        time.sleep(1) 
        response = model.generate_content(prompt)
        ai_text = response.text
        
        # Discordへの通知（重要な銘柄情報として送信）
        webhook_msg = f"🚀 **【AI予報】{name} ({symbol})**\n現値: {last_price:,.0f}円\n{ai_text}"
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=webhook_msg).execute()
        
        return ai_text
    except:
        return "AI分析待機中...（API制限。少し時間を置いて再試行してください）"

# --- メイン UI ---
st.title("🏆 Jack株AI：最終兵器ダッシュボード")

# プライム市場の主要銘柄（ジャックさんの監視対象）
target_stocks = {
    "8035.T": "東エレク", "9984.T": "SBG", "6758.T": "ソニーG", 
    "7203.T": "トヨタ", "6920.T": "レーザーテク", "6857.T": "アドバンテ",
    "6146.T": "ディスコ", "4063.T": "信越化", "8058.T": "三菱商",
    "8316.T": "三井住友", "9101.T": "日本郵船", "7011.T": "三菱重"
}

if st.button("🚀 AIフルスキャン ＆ 攻略本作成を開始"):
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 処理を高速化するためのリスト
    items = list(target_stocks.items())
    
    for i, (symbol, name) in enumerate(items):
        status_text.text(f"分析中 ({i+1}/{len(items)}): {name}...")
        
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="3mo")
            
            if not df.empty:
                # テクニカル指標（RSI / RCI / MACD）
                df['RSI'] = ta.rsi(df['Close'], length=14)
                df['RCI'] = ta.rci(df['Close'], length=9)
                
                # AI分析
                ai_insight = analyze_stock_ai(symbol, name, df)
                
                results.append({
                    "銘柄": f"{name} ({symbol})",
                    "現在値": f"{df['Close'].iloc[-1]:,.0f}円",
                    "RSI": round(df['RSI'].iloc[-1], 1),
                    "RCI": round(df['RCI'].iloc[-1], 1),
                    "AI攻略予報": ai_insight
                })
        except Exception as e:
            st.error(f"{name} の取得に失敗しました。")
            
        progress_bar.progress((i + 1) / len(items))

    status_text.text("✅ スキャン完了！Discordを確認してください。")

    # 結果の表示
    st.divider()
    for res in results:
        with st.expander(f"💎 {res['銘柄']} - {res['現在値']}"):
            c1, c2 = st.columns([1, 3])
            c1.metric("RSI", res['RSI'])
            c1.metric("RCI", res['RCI'])
            c2.markdown(f"**【AIによる翌日攻略本】**\n\n{res['AI攻略予報']}")

st.sidebar.markdown("""
### 💡 使い方
1. ボタンを押すと、Geminiが分析を開始。
2. 分析が終わるたびに **Discord** へ自動で通知が飛びます。
3. RSI/RCIで過熱感をチェックしつつ、AIの目標株価を参考に指値を検討してください。
""")
