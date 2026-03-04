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

# --- 📋 リスト取得 ---
def get_prime_tickers():
    try:
        res = requests.get(JPX_LIST_URL, timeout=30)
        # io.BytesIOを使用してFutureWarningを回避
        df = pd.read_excel(io.BytesIO(res.content))
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
        return name_map
    except Exception as e:
        print(f"JPX取得エラー: {e}")
        return {"7203.T":"トヨタ", "9432.T":"NTT", "9984.T":"ソフトバンクG"}

# --- 📈 テクニカル計算 ---
def calculate_rsi(series, period=14):
    if len(series) < period: return pd.Series([np.nan]*len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- 📡 1. 日足全件スキャン（対ブロック仕様） ---
def run_full_daily_scan():
    send_discord("🔍 **【Jack株AI】全件スキャンを開始します（低速・確実モード）...**")
    name_map = get_prime_tickers()
    tickers = list(name_map.keys())
    hits = {}
    
    # ✅ 改善：ブロックを避けるため20銘柄ずつ小分けにする
    chunk_size = 20
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i : i + chunk_size]
        try:
            # ✅ 改善：threads=Falseでアクセスを1本に絞り、お行儀よく取得する
            data = yf.download(batch, period="1mo", progress=False, threads=False)['Close']
            
            # バッチ内の各銘柄を精査
            for t in batch:
                if t not in data or data[t].isnull().all(): continue
                c = data[t].dropna()
                if len(c) < 15: continue
                rsi = calculate_rsi(c, 14).iloc[-1]
                
                # RSI 20以下 または 80以上 をお宝検知
                if not np.isnan(rsi):
                    if rsi <= 20 or rsi >= 85:
                        status = "📉 底圏" if rsi <= 20 else "📈 天井"
                        hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f})"}
        except Exception as e:
            print(f"Batch {i} error: {e}")
            time.sleep(10) # エラー時は長めに休む
        
        # ✅ 改善：各バッチごとに3秒休む（Yahooへのマナー）
        time.sleep(3)
        if i % 200 == 0: print(f"📊 進捗: {i}/{len(tickers)} 完了...")

    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f, ensure_ascii=False, indent=2)
    send_discord(f"✨ **【スキャン完了】** 本日のお宝候補は **{len(hits)}件** です。")

if __name__ == "__main__":
    now_jst = get_jst_now()
    # 常に最新を取りたいため日付が変わっていれば実行
    run_full_daily_scan()
