import yfinance as yf
import pandas as pd
from google import genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os

# --- 設定 ---
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY") 
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

if not GENAI_API_KEY:
    print("❌ エラー: APIキーが見つかりません。")
    exit()

client = genai.Client(api_key=GENAI_API_KEY)

# --- 1. プライム銘柄自動取得 (xlrd対応) ---
def get_prime_tickers():
    print("📡 JPXからプライム銘柄リストを自動取得中...")
    try:
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        # xlrdをエンジンに指定してExcelを読み込む
        df = pd.read_excel(url, engine='xlrd')
        prime_stocks = df[df["市場・商品区分"] == "プライム（内国株式）"]
        return {f"{row['コード']}.T": row['銘柄名'] for _, row in prime_stocks.iterrows()}
    except Exception as e:
        print(f"⚠️ リスト取得失敗: {e}。主要銘柄で代替します。")
        return {"8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6920.T": "レーザーテック"}

# --- 2. テクニカル計算 ---
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

# --- 3. メインスキャン ---
def run_full_scan():
    TICKER_MAP = get_prime_tickers()
    all_data = []
    summary_text = ""
    
    # 処理負荷を抑えるため、上位150銘柄程度を精査（調整可能）
    for i, (symbol, name) in enumerate(list(TICKER_MAP.items())[:150]):
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty or len(df) < 20: continue
            
            rsi = round(calculate_rsi(df['Close'], 14).iloc[-1], 1)
            rci = round(calculate_rci(df['Close'], 9)[-1], 1)
            price = df['Close'].iloc[-1]
            
            # --- ジャックさん専用：超絶アラート判定 ---
            alert = ""
            if rsi < 21 and rci < -79:
                alert = "🔥【超絶売られすぎ・反発期待】\n"
            elif rsi > 89 and rci > 94:
                alert = "⚠️【超過熱・高値警戒】\n"
            
            if alert or (i < 30): # アラート銘柄または主要銘柄を優先
                summary_text += f"{alert}{name}({symbol}): RSI:{rsi}, RCI:{rci}, 価格:{price:,.0f}円\n"
        except: continue

    # 🤖 AI一括分析 (404エラー対策: モデル名をIDのみで指定)
    prompt = f"日本株のプロとして以下を分析し、変動要因、上昇期待日、目標株価を銘柄ごとに3行で回答せよ。\n\n{summary_text}"
    try:
        # 最新のSDK形式に合わせ、モデル名をシンプルに指定
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=prompt
        )
        ai_analysis = response.text
    except Exception as e:
        ai_analysis = f"AI分析エラー: {str(e)}"

    # 📢 Discord送信
    now_str = datetime.now().strftime('%m/%d %H:%M')
    msg = f"📢 **【Jack株AI 定刻報告】** ({now_str})\n\n{ai_analysis}"
    for i in range(0, len(msg), 1900):
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg[i:i+1900]).execute()
    
    print(f"✅ スキャン完了")

if __name__ == "__main__":
    run_full_scan()

