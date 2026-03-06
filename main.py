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
    print("❌ APIキーが読み込めていません。")
    exit()

client = genai.Client(api_key=GENAI_API_KEY)

# --- 1. 銘柄自動取得リストの作成 ---
def get_prime_ticker_list():
    """JPXの公式サイトからプライム市場の全銘柄リストを取得・抽出する"""
    print("📡 JPXからプライム銘柄リストを自動取得中...")
    try:
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        df_jpx = pd.read_excel(url)
        # 市場区分が「プライム」の銘柄のみ抽出
        prime_df = df_jpx[df_jpx["市場・商品区分"] == "プライム（内国株式）"]
        # コードを yfinance 形式 (例: 8035.T) に変換
        ticker_list = [f"{code}.T" for code in prime_df["コード"]]
        # 銘柄名とのマップを作成
        ticker_map = dict(zip(ticker_list, prime_df["銘柄名"]))
        return ticker_map
    except Exception as e:
        print(f"⚠️ リスト取得失敗。固定リストを使用します: {e}")
        return {"8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG"}

# --- 2. テクニカル計算 (ジャックさん専用ロジック) ---
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

# --- 3. AI一括分析 ---
def get_batch_ai_analysis(stock_data_list):
    input_text = "\n".join([f"{d['alert']}{d['name']}({d['symbol']}): 価格{d['price']}円, RSI{d['rsi']}, RCI{d['rci']}" for d in stock_data_list])
    prompt = f"""
    あなたは凄腕のテクニカルトレーダーです。以下の日本株（特にアラート銘柄）について、
    変動要因、上昇期待日、目標株価を3行で簡潔に分析してください。
    【対象銘柄】
    {input_text}
    """
    try:
        time.sleep(15) 
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return response.text if response.text else "分析失敗"
    except Exception as e:
        return f"AIエラー: {str(e)}"

# --- 4. メインスキャン実行 ---
def run_full_scan():
    TICKER_MAP = get_prime_ticker_list()
    print(f"🚀 プライム市場 {len(TICKER_MAP)} 銘柄のスキャンを開始...")
    
    all_stock_data = []
    
    for symbol, name in TICKER_MAP.items():
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty or len(df) < 20: continue
            
            last_p = df['Close'].iloc[-1]
            # 以前の条件: 株価3,000円以上の高出来高銘柄を優先
            if last_p < 3000: continue
            
            rsi = calculate_rsi(df['Close'], 14).iloc[-1]
            rci = calculate_rci(df['Close'], 9)[-1]
            
            # --- ジャックさん指定の緊急アラート判定 ---
            alert_prefix = ""
            if rsi < 21 and rci < -79:
                alert_prefix = "🔥【超絶売られすぎ・反発期待】\n"
            elif rsi > 89 and rci > 94:
                alert_prefix = "⚠️【超過熱・高値警戒】\n"
            
            # アラートが出ている銘柄、または主要24銘柄のみをAI分析対象にする
            # (全銘柄送るとリミットに達するため、条件合致を優先)
            if alert_prefix or len(all_stock_data) < 24:
                all_stock_data.append({
                    "symbol": symbol, "name": name, "price": f"{last_p:,.0f}",
                    "rsi": round(rsi, 1), "rci": round(rci, 1), "alert": alert_prefix
                })
                print(f"✅ {name} をリストに追加")
                
        except: continue

    # 結果をDiscordへ
    final_report = f"📢 **【Jack株AI 定刻報告】** ({datetime.now().strftime('%m/%d %H:%M')})\n"
    batch_size = 5
    for i in range(0, len(all_stock_data), batch_size):
        batch = all_stock_data[i:i + batch_size]
        analysis_result = get_batch_ai_analysis(batch)
        final_report += analysis_result + "\n\n---\n\n"

    for j in range(0, len(final_report), 1900):
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=final_report[j:j+1900]).execute()
    print("✅ 完了")

if __name__ == "__main__":
    run_full_scan()

