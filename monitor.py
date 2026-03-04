import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import io
import numpy as np
from datetime import datetime, timedelta, timezone, time as dt_time

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
PRE_SCAN_FILE = "pre_scan_results.json"
WATCHLIST_FILE = "jack_watchlist.json"
JPX_LIST_URL = "https://www.jpx.co.jp/markets/statistics-banner/quote/tvdivq0000001vg2-att/data_j.xls"

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_discord(msg):
    try: requests.post(DISCORD_URL, json={"content": msg}, timeout=10)
    except: print(f"Discord送信失敗: {msg}")

# --- 📈 テクニカル計算 ---
def calculate_rsi(series, period=14):
    if len(series) < period: return pd.Series([np.nan]*len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- 📡 1. 高速日足全件スキャン ---
def run_full_daily_scan():
    print("🚀 全件スキャンを開始します...")
    send_discord("🔍 **【Jack株AI】プライム市場全件スキャンを開始します（Excel読み込み中）...**")
    
    name_map = {}
    try:
        res = requests.get(JPX_LIST_URL, timeout=30)
        # ✅ 修正：engine='xlrd' を指定して.xlsを確実に読み込む
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        send_discord(f"⚠️ リスト取得失敗: {e}")
        name_map = {"7203.T":"トヨタ", "9432.T":"NTT", "9984.T":"ソフトバンクG"}

    tickers = list(name_map.keys())
    hits = {}
    chunk_size = 25 # ブロック回避と速度のバランス
    
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i : i + chunk_size]
        try:
            # threads=False で順番に取得し、Yahooの警告を回避
            data = yf.download(batch, period="1mo", progress=False, threads=False)['Close']
            for t in batch:
                if t not in data or data[t].isnull().all(): continue
                c = data[t].dropna()
                if len(c) < 15: continue
                rsi = calculate_rsi(c, 14).iloc[-1]
                
                # RSI 25以下 または 80以上 を検知
                if not np.isnan(rsi):
                    if rsi <= 25 or rsi >= 80:
                        status = "📉 底圏" if rsi <= 25 else "📈 天井"
                        hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f})"}
        except:
            time.sleep(5) # エラー時は少し休む
        
        time.sleep(2) # 2秒待機
        if i % 250 == 0: print(f"📊 スキャン進捗: {i}/{len(tickers)}...")

    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f, ensure_ascii=False, indent=2)
    send_discord(f"✨ **【スキャン完了】** お宝候補は **{len(hits)}件** です。")

if __name__ == "__main__":
    run_full_daily_scan()
