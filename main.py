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
    print("❌ APIキーが読み込めていません。GitHubのSettings > Secretsを確認してください。")
    exit()

client = genai.Client(api_key=GENAI_API_KEY)

# 🏆 プライム市場 厳選100銘柄リスト（和名対応）
TICKER_MAP = {
    "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6758.T": "ソニーG", "7203.T": "トヨタ自動車",
    "6920.T": "レーザーテック", "6857.T": "アドバンテスト", "6146.T": "ディスコ", "4063.T": "信越化学",
    "8058.T": "三菱商事", "8316.T": "三井住友FG", "9101.T": "日本郵船", "7011.T": "三菱重工",
    "4502.T": "武田薬品", "6501.T": "日立製作所", "6702.T": "富士通", "6201.T": "豊田自動織機",
    "9104.T": "商船三井", "6367.T": "ダイキン工業", "6273.T": "SMC", "7974.T": "任天堂",
    "9020.T": "JR東日本", "2914.T": "JT", "4061.T": "デンカ", "6723.T": "ルネサス",
    "4503.T": "アステラス薬", "6098.T": "リクルート", "6902.T": "デンソー", "6981.T": "村田製作所",
    "7741.T": "ＨＯＹＡ", "8001.T": "伊藤忠", "8031.T": "三井物産", "8306.T": "三菱ＵＦＪ",
    "8411.T": "みずほＦＧ", "8766.T": "東京海上", "8801.T": "三井不動産", "8802.T": "三菱地所",
    "9432.T": "ＮＴＴ", "9433.T": "ＫＤＤＩ", "9983.T": "ファーストリテイ", "4901.T": "富士フイルム",
    "5108.T": "ブリヂストン", "6301.T": "小松製作所", "6503.T": "三菱電機", "7751.T": "キヤノン",
    # 銘柄は順次追加可能
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
    $$RCI = (1 - \\frac{6 \sum d^2}{n(n^2 - 1)}) \times 100$$
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
    input_text = "\n".join([f"{d['name']}({d['symbol']}): 価格{d['price']}円, RSI{d['rsi']}, RCI{d['rci']}" for d in stock_data_list])
    prompt = f"以下の日本株について、テクニカル視点から変動要因、上昇期待日、目標株価を銘柄ごとに3行で簡潔に分析してください。\n\n{input_text}"
    try:
        print("🤖 AI分析中...")
        time.sleep(15) 
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return response.text if response.text else "分析失敗"
    except Exception as e:
        return f"エラー: {str(e)}"

def run_full_scan():
    print("🚀 スキャン開始...")
    all_stock_data = []
    
    # 銘柄リストをループ
    for symbol, name in TICKER_MAP.items():
        try:
            print(f"📡 データ取得中: {name} ({symbol})")
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            
            if df.empty or len(df) < 20:
                print(f"⚠️ {name} のデータが空です。スキップします。")
                continue
            
            rsi = calculate_rsi(df['Close'], 14).iloc[-1]
            rci = calculate_rci(df['Close'], 9)[-1]
            
            all_stock_data.append({
                "symbol": symbol, "name": name, 
                "price": f"{df['Close'].iloc[-1]:,.0f}",
                "rsi": round(rsi, 1) if not np.isnan(rsi) else 0,
                "rci": round(rci, 1) if not np.isnan(rci) else 0
            })
        except Exception as e:
            print(f"❌ {symbol} 取得失敗: {e}")
            continue

    if not all_stock_data:
        msg = "❌ 条件に合致する銘柄データが取得できませんでした。yfinanceの制限の可能性があります。"
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg).execute()
        print(msg)
        return

    # AI分析
    final_report = f"📢 **【Jack株AI 定刻報告】** ({datetime.now().strftime('%H:%M')})\n"
    final_report += f"📊 対象銘柄数: {len(all_stock_data)}銘柄\n\n"
    
    batch_size = 5
    for i in range(0, len(all_stock_data), batch_size):
        batch = all_stock_data[i:i + batch_size]
        analysis_result = get_batch_ai_analysis(batch)
        final_report += analysis_result + "\n\n---\n\n"

    # Discordへ送信
    for j in range(0, len(final_report), 1900):
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=final_report[j:j+1900]).execute()
    
    print("✅ 完了")

if __name__ == "__main__":
    run_full_scan()
