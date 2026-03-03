import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

TICKER_NAMES = {"2502.T": "アサヒ", "5401.T": "日本製鉄", "7267.T": "ホンダ", "9020.T": "JR東日本", "9432.T": "NTT", "9433.T": "KDDI"}
PRIME_TICKERS = list(TICKER_NAMES.keys()) + ["1605.T", "1801.T", "7203.T", "9984.T"] # 必要に応じて追加

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

def run_prime_prescan():
    print(f"📡 スキャン開始時刻: {get_jst_now()}")
    hits = {}
    try:
        data = yf.download(PRIME_TICKERS, period="3mo", progress=False)['Close']
        for t in PRIME_TICKERS:
            c = data[t].dropna()
            if len(c) < 15: continue
            rsi = calculate_rsi(c).tail(5).min()
            # 💡 RSIが35以下のものだけを検知（テスト時は数値を上げてください）
            if rsi <= 45: 
                hits[t] = f"RSI:{rsi:.1f}"
    except Exception as e:
        print(f"❌ エラー: {e}")
    
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
    print(f"🏁 スキャン完了：{len(hits)}件保存")

# (以下 monitor_cycle 等は以前と同じ)
if __name__ == "__main__":
    now_t = get_jst_now().time()
    if not os.path.exists(PRE_SCAN_FILE) or (dt_time(9, 10) <= now_t <= dt_time(9, 20)):
        run_prime_prescan()
    # 監視サイクル実行...
