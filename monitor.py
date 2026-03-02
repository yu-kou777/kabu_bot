import yfinance as yf
import pandas as pd
import json
import os
import time
from datetime import datetime, timedelta, timezone, time as dt_time

# --- 設定 ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json" # 事前スキャン結果の保存先
from prime_tickers import PRIME_TICKERS # 約1600銘柄のリスト

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

def run_prime_prescan():
    """プライム全件を4バッチで自動スキャン (09:15に実行)"""
    print(f"🚀 事前スキャン開始: {get_jst_now()}")
    all_tickers = PRIME_TICKERS
    n = len(all_tickers)
    chunk_size = n // 4
    hits = {}

    for i in range(4):
        start, end = i * chunk_size, ((i + 1) * chunk_size if i != 3 else n)
        chunk = all_tickers[start:end]
        try:
            data = yf.download(chunk, period="3mo", progress=False)['Close']
            for t in chunk:
                close = data[t].dropna()
                if len(close) < 15: continue
                rsi = calculate_rsi(close).tail(5).min()
                if rsi <= 35: # しきい値35固定
                    hits[t] = f"RSI:{rsi:.1f}"
        except: continue
        time.sleep(2) # サーバー負荷軽減

    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
    print(f"🏁 事前スキャン完了: {len(hits)}件検知")

# --- メインループ ---
if __name__ == "__main__":
    last_scan_date = ""
    while True:
        now = get_jst_now()
        current_date = now.strftime('%Y-%m-%d')
        
        # ✅ 朝 09:15 になったら自動で全件スキャンを実行
        if now.time() >= dt_time(9, 15) and last_scan_date != current_date:
            run_prime_prescan()
            last_scan_date = current_date
        
        # 通常の監視処理（jack_watchlist.jsonがある場合）
        # (ここに前述の5分おき監視ロジックが入ります)
        
        time.sleep(60)
