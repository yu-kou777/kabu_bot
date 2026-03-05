import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import google.generativeai as genai
from discord_webhook import DiscordWebhook
import time

# --- 設定（ジャックさんの情報を反映済み） ---
GENAI_API_KEY = "gen-lang-client-0447054408"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="Jack株AI：最終兵器", layout="wide")

# --- 銘柄リスト (ここを自由に増やしてください) ---
TICKERS = [
    "8035.T", "9984.T", "6758.T", "7203.T", "6920.T", "6857.T", "6146.T", "4063.T",
    "8058.T", "8316.T", "9101.T", "7011.T", "4502.T", "6501.T", "6702.T", "6201.T",
    "9104.T", "6367.T", "6273.T", "7974.T", "9020.T", "2914.T", "4061.T", "6723.T"
]

def analyze_and_notify(symbol, df):
    """AI分析を行い、結果をDiscordに飛ばす"""
    last = df.iloc[-1]
    prompt = f"""
    銘柄コード:{symbol}, 現在値:{last['Close']:.0f}円, RSI:{last['RSI']:.1f}, RCI:{last['RCI']:.1f}
    上記データに基づき、プロの投資家として「変動要因」「上昇予想日」「目標株価」を3行で回答してください。
    """
    try:
        response = model.generate_content(prompt)
        ai_text = response.text
        # Discord送信
        msg = f"🚀 **【AI分析完了】{symbol}**\n現値: {last['Close']:,.0f}円\n{ai_text}"
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg).execute()
        return ai_text
    except:
        return "APIリミットのため、少し待機して再試行してください。"

# --- メイン画面レイアウト ---
st.title("🏆 Jack株AI：最終兵器ダッシュボード")
st.markdown("### プライム市場 100銘柄規模 フルスキャン実行")

if st.button("🚀 フルスキャン ＆ 攻略本作成を開始"):
    results = []
    progress_bar = st.progress(0)
    status_area = st.empty()
    
    # スキャン実行
    for i, symbol in enumerate(TICKERS):
        status_area.write(f"🔍 分析中 ({i+1}/{len(TICKERS)}): {symbol}")
        
        try:
            # データ取得
            stock = yf.Ticker(symbol)
            df = stock.history(period="3mo")
            
            if not df.empty:
                # テクニカル指標計算
                df['RSI'] = ta.rsi(df['Close'], length=14)
                df['RCI'] = ta.rci(df['Close'], length=9)
                
                # API制限回避のウェイト
                if i % 5 == 0 and i > 0:
                    time.sleep(10)
                
                # AI分析 & Discord
                ai_result = analyze_and_notify(symbol, df)
                
                # 結果をリストに追加
                results.append({
                    "銘柄": symbol,
                    "現在値": f"{df['Close'].iloc[-1]:,.0f}円",
                    "RSI": round(df['RSI'].iloc[-1], 1),
                    "RCI": round(df['RCI'].iloc[-1], 1),
                    "AI予報": ai_result
                })
            
            # 1銘柄ごとの待機
            time.sleep(1)
            
        except Exception as e:
            st.error(f"{symbol} でエラー発生: {e}")
            
        progress_bar.progress((i + 1) / len(TICKERS))

    status_area.success("✅ 全銘柄の分析が完了しました！")

    # テーブル形式で画面に表示
    st.divider()
    st.subheader("📊 スキャン結果一覧")
    st.dataframe(pd.DataFrame(results), use_container_width=True)

    # 詳細カード表示
    for res in results:
        with st.expander(f"💎 {res['銘柄']} の詳細攻略予報"):
            st.write(res['AI予報'])
