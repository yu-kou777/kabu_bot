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

client = genai.Client(api_key=GENAI_API_KEY)

# 監視対象（JPXから自動取得する機能は計算負荷が高いため、まずは100銘柄リストを保持）
TICKER_MAP = {
    "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6758.T": "ソニーG", "7203.T": "トヨタ自動車",
    "6920.T": "レーザーテック", "6857.T": "アドバンテスト", "6146.T": "ディスコ", "4063.T": "信越化学",
    "8058.T": "三菱商事", "8316.T": "三井住友FG", "9101.T": "日本郵船", "7011.T": "三菱重工",
    # 銘柄リストをここに追加...
}

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_rci(series, period=9):
    """
    RCIの計算公式:
    $$RCI = \left( 1 - \frac{6 \sum d^2}{n(n^2 - 1)} \right) \times 100$$
    """
    if len(series) < period: return np.zeros(len(series))
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

def get_batch_ai_analysis(stock_data_list):
    input_text = ""
    for d in stock_data_list:
        alert = ""
        # ジャックさん指定の緊急アラート判定
        if d['rsi'] < 21 and d['rci'] < -79:
            alert = "🔥【超絶売られすぎ・反発期待】"
        elif d['rsi'] > 89 and d['rci'] > 94:
            alert = "⚠️【超過熱・高値警戒】"
        input_text += f"{alert}{d['name']}({d['symbol']}): 価格{d['price']}円, RSI{d['rsi']}, RCI{d['rci']}\n"
    
    prompt = f"以下の日本株について、テクニカル視点から変動要因、上昇期待日、目標株価を銘柄ごとに3行で簡潔に分析してください。\n\n{input_text}"
    
    for attempt in range(3):
        try:
            print(f"🤖 AI分析中 (試行 {attempt+1})...")
            # 待機時間を30秒に延長してエラーを回避
            time.sleep(30) 
            # より安定した1.5-flashを使用
            response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
            return response.text if response.text else "分析失敗"
        except Exception as e:
            if "429" in str(e):
                print("⏳ 制限回避のため1分待機します...")
                time.sleep(60)
            else:
                return f"エラー: {str(e)}"
    return "分析制限により取得不可"

def run_full_scan():
    print("🚀 スキャン開始...")
    all_stock_data = []
    
    for symbol, name in TICKER_MAP.items():
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty or len(df) < 20: continue
            
            rsi = calculate_rsi(df['Close'], 14).iloc[-1]
            rci = calculate_rci(df['Close'], 9)[-1]
            
            all_stock_data.append({
                "date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "symbol": symbol, "name": name, 
                "price": df['Close'].iloc[-1],
                "rsi": round(rsi, 1) if not np.isnan(rsi) else 0,
                "rci": round(rci, 1) if not np.isnan(rci) else 0
            })
        except: continue

    if not all_stock_data: return

    # AI分析
    final_report = f"📢 **【Jack株AI 定刻報告】** ({datetime.now().strftime('%m/%d %H:%M')})\n\n"
    results_for_csv = []
    
    batch_size = 5
    for i in range(0, len(all_stock_data), batch_size):
        batch = all_stock_data[i:i + batch_size]
        analysis_result = get_batch_ai_analysis(batch)
        final_report += analysis_result + "\n\n---\n\n"
        
        # 履歴保存用のデータを整理
        for d in batch:
            d["ai_analysis"] = analysis_result # 簡易的にバッチ結果を保存
            results_for_csv.append(d)

    # --- 履歴の保存 ---
    df_new = pd.DataFrame(results_for_csv)
    # CSVに追記保存
    history_file = "scan_history.csv"
    if os.path.exists(history_file):
        df_new.to_csv(history_file, mode='a', header=False, index=False)
    else:
        df_new.to_csv(history_file, index=False)

    # Discordへ送信
    for j in range(0, len(final_report), 1900):
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=final_report[j:j+1900]).execute()
    
    print("✅ 全工程完了")

if __name__ == "__main__":
    run_full_scan()
