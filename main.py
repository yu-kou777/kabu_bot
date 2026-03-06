import yfinance as yf
import pandas as pd
from google import genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os

# --- 設定 ---
# GitHub Secrets に GEMINI_API_KEY を登録してください
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY") 
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

if not GENAI_API_KEY:
    print("❌ エラー: APIキー(GEMINI_API_KEY)が設定されていません。")
    # GitHub Secretsへの登録が必要です
    exit()

client = genai.Client(api_key=GENAI_API_KEY)

# --- 1. プライム市場の銘柄を自動取得 ---
def get_prime_tickers():
    print("📡 JPXからプライム銘柄リストを取得中...")
    try:
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        df = pd.read_excel(url)
        # プライム市場の銘柄のみ抽出
        prime_stocks = df[df["市場・商品区分"] == "プライム（内国株式）"]
        # 銘柄名とコードを辞書にする (例: 8035.T)
        return {f"{row['コード']}.T": row['銘銘柄名'] for _, row in prime_stocks.iterrows()}
    except Exception as e:
        print(f"⚠️ リスト取得失敗: {e}。固定リストで代替します。")
        return {"8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6920.T": "レーザーテック"}

# --- 2. テクニカル計算 (ジャックさんの要望に基づき実施) ---
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

def run_full_scan():
    print("🚀 スキャン開始...")
    TICKER_MAP = get_prime_tickers()
    all_data = []
    summary_text = ""
    
    # タイムアウトを避けるため、出来高の多い主要銘柄やジャックさんの監視銘柄を優先
    # ここでは例として上位100銘柄規模に絞ることも可能ですが、全件回すロジックにします
    count = 0
    for symbol, name in TICKER_MAP.items():
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty or len(df) < 20: continue
            
            rsi = round(calculate_rsi(df['Close'], 14).iloc[-1], 1)
            rci = round(calculate_rci(df['Close'], 9)[-1], 1)
            price = df['Close'].iloc[-1]
            
            # --- ジャックさん指定のアラート判定 ---
            alert = ""
            if rsi < 21 and rci < -79: 
                alert = "🔥【超絶売られすぎ・反発期待】"
            elif rsi > 89 and rci > 94: 
                alert = "⚠️【超過熱・高値警戒】"
            
            # 条件に合う銘柄、または主要銘柄のみをレポートに含める（無料枠リミット対策）
            if alert or count < 30:
                all_data.append({"銘柄名": name, "コード": symbol, "現値": f"{price:,.0f}円", "RSI": rsi, "RCI": rci, "判定": alert})
                summary_text += f"{alert}{name}({symbol}): RSI:{rsi}, RCI:{rci}, 価格:{price:,.0f}円\n"
                count += 1
        except: continue

    # 🤖 AI一括分析（404エラー対策済み）
    prompt = f"以下の日本株テクニカルデータ（特にアラート銘柄）を分析し、変動要因、上昇期待日、目標株価を銘柄ごとに3行で分析してください。\n\n{summary_text}"
    try:
        # モデル名は 'gemini-1.5-flash' で直接指定
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        ai_analysis = response.text
    except Exception as e:
        ai_analysis = f"AI分析エラー: {str(e)}"

    # 📢 Discord送信
    now_str = datetime.now().strftime('%m/%d %H:%M')
    msg = f"📢 **【Jack株AI 定刻報告】** ({now_str})\n\n{ai_analysis}"
    for i in range(0, len(msg), 1900):
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg[i:i+1900]).execute()
    
    # 完了ログ
    print(f"✅ スキャン完了: {len(all_data)} 銘柄を精査しました。")

if __name__ == "__main__":
    run_full_scan()
