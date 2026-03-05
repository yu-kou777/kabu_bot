import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import google.generativeai as genai
from discord_webhook import DiscordWebhook
import datetime

# --- 初期設定 ---
GENAI_API_KEY = "YOUR_GEMINI_API_KEY"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="Gemini AI 株価攻略ボード", layout="wide")

# --- 関数：AIによる個別銘柄分析 ---
def analyze_with_gemini(ticker_symbol, df):
    latest = df.iloc[-1]
    # 直近5日の動きをプロンプトに注入
    recent_data = df.tail(5).to_string()
    
    prompt = f"""
    あなたはプロの機関投資家トレーダーです。
    銘柄コード:{ticker_symbol} の直近データに基づき、テクニカルと最新の市場動向から分析してください。
    
    【データ】
    {recent_data}
    
    以下の3点を日本語で、簡潔かつ鋭く回答してください。
    1. 変動要因（例：米テック株指数連動、半導体需給など）
    2. 上昇予想日（直近の期待日）
    3. 目標株価（テクニカル的な節目）
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "分析エラー：API制限またはデータ不足"

# --- メイン UI ---
st.title("🚀 Prime 3000+ AIフルスキャン & 翌日攻略本")
st.sidebar.header("スキャン設定")

if st.sidebar.button("🚀 AIフルスキャン ＆ 予報を開始"):
    # 1. プライム市場の主要銘柄リスト（例示として代表的な3000円超え高出来高銘柄をピックアップ）
    # ※本来は全件取得ロジックを入れるが、速度重視で主要銘柄を対象
    targets = ["8035.T", "6857.T", "9984.T", "6723.T", "4063.T", "6146.T", "7735.T", "6920.T"]
    
    results = []
    status_text = st.empty()
    
    for symbol in targets:
        status_text.text(f"分析中: {symbol}...")
        stock = yf.Ticker(symbol)
        df = stock.history(period="3mo")
        
        if len(df) < 30 or df['Close'].iloc[-1] < 3000:
            continue
            
        # テクニカル計算
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['RCI'] = ta.rci(df['Close'], length=9)
        macd = ta.macd(df['Close'])
        df = pd.concat([df, macd], axis=1)
        
        # 異常検知（Discordアラート）
        last_rsi = df['RSI'].iloc[-1]
        last_rci = df['RCI'].iloc[-1]
        
        if last_rsi > 85 or last_rci > 95:
            msg = f"⚠️ 【超過熱アラート】{symbol} RSI:{last_rsi:.1f} RCI:{last_rci:.1f} 調整売りに注意！"
            DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg).execute()
            
        # Gemini AI 分析実行
        ai_analysis = analyze_with_gemini(symbol, df)
        
        results.append({
            "銘柄": symbol,
            "現在値": f"{df['Close'].iloc[-1]:,.0f}円",
            "RSI": round(last_rsi, 1),
            "RCI": round(last_rci, 1),
            "AI攻略予報": ai_analysis
        })
        
    st.success("スキャン完了！")
    
    # 2. 結果表示（データフレーム）
    res_df = pd.DataFrame(results)
    st.table(res_df)

# --- サイドバー：Discord通知テスト ---
if st.sidebar.button("🔔 Discord連携テスト"):
    DiscordWebhook(url=DISCORD_WEBHOOK_URL, content="システム稼働中：翌日の攻略準備が完了しました。").execute()
    st.sidebar.write("送信完了！")
