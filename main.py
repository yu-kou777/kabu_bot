import yfinance as yf
import pandas as pd
from google import genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os

# --- 設定 ---
# GitHub Secretsから安全に読み込みます
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY") 
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

if not GENAI_API_KEY:
    print("❌ APIキーが見つかりません。GitHubのSecretsを確認してください。")
    exit()

client = genai.Client(api_key=GENAI_API_KEY)

TICKER_MAP = {
    "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6758.T": "ソニーG",
    "7203.T": "トヨタ自動車", "6920.T": "レーザーテック", "6857.T": "アドバンテスト",
    "6146.T": "ディスコ", "4063.T": "信越化学", "8058.T": "三菱商事",
    "8316.T": "三井住友FG", "9101.T": "日本郵船", "7011.T": "三菱重工"
}

# --- テクニカル計算 (ジャックさんの要望に基づき実施) ---
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

# --- AI一括分析 ---
def get_batch_ai_analysis(stock_data_list):
    input_text = ""
    for d in stock_data_list:
        alert = ""
        # ジャックさん専用判定：超絶売られすぎ(RSI<21, RCI<-79) / 超過熱(RSI>89, RCI>94)
        if d['rsi'] < 21 and d['rci'] < -79:
            alert = "🔥【超絶売られすぎ・反発期待】\n"
        elif d['rsi'] > 89 and d['rci'] > 94:
            alert = "⚠️【超過熱・高値警戒】\n"
        
        input_text += f"{alert}{d['name']}({d['symbol']}): 価格{d['price']}円, RSI{d['rsi']}, RCI{d['rci']}\n"
    
    # テクニカル分析を重視したプロンプト
    prompt = f"以下の日本株について、テクニカル視点から変動要因、上昇期待日、目標株価を銘柄ごとに3行で簡潔に分析してください。\n\n{input_text}"
    
    try:
        time.sleep(30) # 429エラー回避のため長めに待機
        # 修正：モデル名を正確に指定
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return response.text if response.text else "分析失敗"
    except Exception as e:
        return f"AIエラー: {str(e)}"

def run_full_scan():
    print("🚀 スキャン開始...")
    all_stock_data = []
    
    for symbol, name in TICKER_MAP.items():
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty: continue
            
            rsi = calculate_rsi(df['Close'], 14).iloc[-1]
            rci = calculate_rci(df['Close'], 9)[-1]
            
            all_stock_data.append({
                "symbol": symbol, "name": name, 
                "price": f"{df['Close'].iloc[-1]:,.0f}",
                "rsi": round(rsi, 1), "rci": round(rci, 1)
            })
        except: continue

    final_report = f"📢 **【Jack株AI 定刻報告】** ({datetime.now().strftime('%m/%d %H:%M')})\n\n"
    batch_size = 5
    for i in range(0, len(all_stock_data), batch_size):
        batch = all_stock_data[i:i + batch_size]
        analysis_result = get_batch_ai_analysis(batch)
        final_report += analysis_result + "\n\n---\n\n"

    for j in range(0, len(final_report), 1900):
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=final_report[j:j+1900]).execute()
    print("✅ 全工程完了")

if __name__ == "__main__":
    run_full_scan()
