import yfinance as yf
import pandas as pd
from google import genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os
import json
import gspread
from google.oauth2.service_account import Credentials

# --- 設定 ---
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY") 
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
SHEET_JSON = os.environ.get("GSPREAD_SERVICE_ACCOUNT")

client = genai.Client(api_key=GENAI_API_KEY)

# 銘柄自動取得（簡易版：まずは主要銘柄を対象）
def get_target_tickers():
    return {
        "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6758.T": "ソニーG",
        "7203.T": "トヨタ自動車", "6920.T": "レーザーテック", "6857.T": "アドバンテスト",
        "6146.T": "ディスコ", "4063.T": "信越化学", "8058.T": "三菱商事"
    }

# スプレッドシート保存関数
def save_to_sheets(data_list):
    if not SHEET_JSON: return
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(json.loads(SHEET_JSON), scopes=scopes)
        gc = gspread.authorize(creds)
        # 「Jack_Stock_History」という名前のスプレッドシートをあらかじめ作成し共有しておく必要があります
        sh = gc.open("Jack_Stock_History").sheet1
        for d in data_list:
            sh.append_row([d['date'], d['symbol'], d['name'], d['price'], d['rsi'], d['rci'], d['analysis']])
    except Exception as e:
        print(f"❌ スプレッドシート保存失敗: {e}")

# テクニカル計算 (RCI公式:)
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

def get_batch_ai_analysis(stock_data_list):
    input_text = ""
    for d in stock_data_list:
        alert = ""
        if d['rsi'] < 21 and d['rci'] < -79: alert = "🔥【超絶売られすぎ】"
        elif d['rsi'] > 89 and d['rci'] > 94: alert = "⚠️【超過熱・警戒】"
        input_text += f"{alert}{d['name']}({d['symbol']}): 価格{d['price']}円, RSI{d['rsi']}, RCI{d['rci']}\n"
    
    prompt = f"日本株のテクニカル分析。変動要因、上昇期待日、目標株価を銘柄ごとに3行で分析せよ。\n\n{input_text}"
    
    try:
        time.sleep(30)
        # 修正：モデル名を正確に指定
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        return response.text if response.text else "分析失敗"
    except Exception as e:
        return f"エラー: {str(e)}"

def run_full_scan():
    TICKER_MAP = get_target_tickers()
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
                "date": datetime.now().strftime('%Y-%m-%d %H:%M'),
                "symbol": symbol, "name": name, 
                "price": f"{df['Close'].iloc[-1]:,.0f}",
                "rsi": round(rsi, 1), "rci": round(rci, 1)
            })
        except: continue

    final_report = f"📢 **【Jack株AI 定刻報告】** ({datetime.now().strftime('%m/%d %H:%M')})\n\n"
    history_to_save = []
    
    batch_size = 5
    for i in range(0, len(all_stock_data), batch_size):
        batch = all_stock_data[i:i + batch_size]
        analysis_result = get_batch_ai_analysis(batch)
        final_report += analysis_result + "\n\n---\n\n"
        for d in batch:
            d['analysis'] = analysis_result
            history_to_save.append(d)

    # Discord送信
    for j in range(0, len(final_report), 1900):
        DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=final_report[j:j+1900]).execute()
    
    # スプレッドシート保存
    save_to_sheets(history_to_save)
    print("✅ 完了")

if __name__ == "__main__":
    run_full_scan()

