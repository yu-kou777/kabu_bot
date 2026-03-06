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
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") # Secretsに登録してください

client = genai.Client(api_key=GENAI_API_KEY)

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
    print("🚀 スキャン開始（Jack株AI v100）...")
    
    # 銘柄リスト（JPXが不安定な時のためのフォールバック）
    TICKER_MAP = {
        "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6758.T": "ソニーG",
        "7203.T": "トヨタ自動車", "6920.T": "レーザーテック", "6857.T": "アドバンテスト",
        "6146.T": "ディスコ", "4063.T": "信越化学", "8058.T": "三菱商事",
        "8316.T": "三井住友FG", "9101.T": "日本郵船", "7011.T": "三菱重工"
    }
    
    scan_summary = ""
    hit_count = 0

    for symbol, name in TICKER_MAP.items():
        try:
            print(f"📡 データ取得中: {name}({symbol})")
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty:
                print(f"  ⚠️ {name} データなし")
                continue
            
            rsi = round(calculate_rsi(df['Close'], 14).iloc[-1], 1)
            rci = round(calculate_rci(df['Close'], 9)[-1], 1)
            price = f"{df['Close'].iloc[-1]:,.0f}"
            
            # ジャックさん指定の緊急アラート判定
            alert = ""
            if rsi < 21 and rci < -79:
                alert = "🔥【超絶売られすぎ】"
            elif rsi > 89 and rci > 94:
                alert = "⚠️【超過熱・警戒】"
            
            print(f"  ✅ RSI:{rsi} / RCI:{rci} {alert}")
            scan_summary += f"{alert}{name}({symbol}): RSI:{rsi}, RCI:{rci}, 価格:{price}円\n"
            hit_count += 1
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            continue

    if hit_count == 0:
        print("❌ 解析対象の銘柄が見つかりませんでした。")
        return

    # 🤖 AI一括分析
    print("🤖 AIが攻略本を執筆中...")
    prompt = f"凄腕トレーダーとして以下を分析。変動要因、上昇期待日、目標株価を銘柄ごとに3行で回答せよ。\n\n{scan_summary}"
    try:
        time.sleep(15) # API制限回避
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        ai_analysis = response.text
    except Exception as e:
        ai_analysis = f"AI分析エラー: {str(e)}"

    # 📢 Discord送信
    now_str = datetime.now().strftime('%m/%d %H:%M')
    msg = f"📢 **【Jack株AI 定刻報告】** ({now_str})\n\n{ai_analysis}"
    DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg).execute()
    print("✅ 全工程が正常に完了し、Discordへ送信しました。")

if __name__ == "__main__":
    run_full_scan()
