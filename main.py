import yfinance as yf
import pandas as pd
from google import genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os

# --- 設定 ---
# GitHub Secrets に登録した GEMINI_API_KEY を使用
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY") 
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

if not GENAI_API_KEY:
    print("❌ エラー: APIキー(GEMINI_API_KEY)が設定されていません。")
    exit()

client = genai.Client(api_key=GENAI_API_KEY)

# --- 1. プライム市場の銘柄を自動取得 ---
def get_prime_tickers():
    print("📡 JPXからプライム銘柄リストを自動取得中...")
    try:
        # JPXの公式サイトから最新の銘柄一覧Excelを取得
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        df = pd.read_excel(url)
        # 「プライム」市場の銘柄のみ抽出
        prime_stocks = df[df["市場・商品区分"] == "プライム（内国株式）"]
        # yfinance形式 (例: 8035.T) の辞書を作成
        return {f"{row['コード']}.T": row['銘柄名'] for _, row in prime_stocks.iterrows()}
    except Exception as e:
        print(f"⚠️ リスト取得失敗: {e}。主要銘柄で代替します。")
        return {"8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6920.T": "レーザーテック"}

# --- 2. テクニカル計算 (ジャックさんの要望に基づくロジック) ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_rci(series, period=9):
    """RCI計算: 順位相関係数を用いたテクニカル指標"""
    if len(series) < period: return np.zeros(len(series))
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        # RCIの公式: (1 - (6 * 差の2乗和) / (n * (n^2 - 1))) * 100
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

# --- 3. メインスキャン実行 ---
def run_full_scan():
    print("🚀 スキャン開始...")
    TICKER_MAP = get_prime_tickers()
    all_hits = []
    summary_text = ""
    
    # 処理負荷とAPI制限を考慮し、まずは上位銘柄や条件合致銘柄を優先
    for i, (symbol, name) in enumerate(TICKER_MAP.items()):
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty or len(df) < 20: continue
            
            # テクニカル指標の算出
            rsi = round(calculate_rsi(df['Close'], 14).iloc[-1], 1)
            rci = round(calculate_rci(df['Close'], 9)[-1], 1)
            price = df['Close'].iloc[-1]
            
            # --- ジャックさん指定の緊急アラート判定 ---
            alert = ""
            if rsi < 21 and rci < -79:
                alert = "🔥【超絶売られすぎ・反発期待】"
            elif rsi > 89 and rci > 94:
                alert = "⚠️【超過熱・高値警戒】"
            
            # アラート銘柄、または主要な変化があるもののみAI分析に回す
            if alert or (i < 50): # 無料枠制限のため初期は50銘柄程度を優先
                all_hits.append({"name": name, "symbol": symbol, "price": f"{price:,.0f}", "rsi": rsi, "rci": rci, "alert": alert})
                summary_text += f"{alert}{name}({symbol}): 価格{price:,.0f}円, RSI:{rsi}, RCI:{rci}\n"
        except: continue

    # 🤖 AI一括分析 (Gemini 1.5 Flash 無料枠を使用)
    prompt = f"凄腕トレーダーとして以下の銘柄（特に🔥や⚠️）を分析し、変動要因、上昇期待日、目標株価を銘柄ごとに3行で分析せよ。\n\n{summary_text}"
    try:
        # API制限回避のため、バッチ処理で1回だけAIを呼ぶ
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        ai_analysis = response.text
    except Exception as e:
        ai_analysis = f"AI分析エラー: {str(e)}"

    # 📢 Discord送信
    now_str = datetime.now().strftime('%m/%d %H:%M')
    msg = f"📢 **【Jack株AI 定刻報告】** ({now_str})\n\n{ai_analysis}"
    for i in range(0, len(msg), 1900):
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg[i:i+1900]).execute()
    
    print(f"✅ スキャン完了: {len(all_hits)} 銘柄を精査しました。")

# --- 実行環境の切り分け ---
# GitHub Actions (CLI) か Streamlit かを判定して確実に実行させる
if __name__ == "__main__":
    import sys
    # Streamlitで実行されていない（＝GitHub Actions等）場合は直接スキャン
    if not any(arg.endswith("streamlit") for arg in sys.argv):
        run_full_scan()
    else:
        # Streamlit用のUI表示
        import streamlit as st
        st.title("🏆 Jack株AI：最終兵器ダッシュボード")
        if st.button("🚀 最新スキャン ＆ 攻略本作成を開始"):
            with st.spinner("AI精査中..."):
                run_full_scan()
                st.success("完了！ Discordに通知しました。")
