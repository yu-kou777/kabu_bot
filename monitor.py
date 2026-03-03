import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time
import numpy as np

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

# 主要プライム銘柄リスト（ここに1000銘柄まで追加可能。まずは50件程度を定義）
PRIME_TICKERS = ["1605.T","1801.T","1802.T","1925.T","2502.T","2802.T","2914.T","3382.T","4063.T","4502.T","4503.T","4519.T","4568.T","4901.T","5401.T","5713.T","6098.T","6301.T","6367.T","6501.T","6758.T","6857.T","6902.T","6920.T","6954.T","6981.T","7203.T","7267.T","7269.T","7741.T","7974.T","8001.T","8031.T","8035.T","8058.T","8306.T","8316.T","8411.T","8766.T","8801.T","9020.T","9101.T","9104.T","9432.T","9433.T","9983.T","9984.T"]

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

def run_prime_prescan():
    """全件を4分割スキャン"""
    print("🚀 事前スキャン実行中...")
    n = len(PRIME_TICKERS)
    chunk = n // 4
    hits = {}
    for i in range(4):
        start, end = i*chunk, ((i+1)*chunk if i!=3 else n)
        batch = PRIME_TICKERS[start:end]
        try:
            data = yf.download(batch, period="3mo", progress=False)['Close']
            for t in batch:
                c = data[t].dropna()
                if len(c) < 15: continue
                rsi = calculate_rsi(c).tail(5).min()
                if rsi <= 35: hits[t] = f"RSI:{rsi:.1f}"
        except: continue
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)

def monitor_cycle():
    """監視リストにある銘柄をチェックしてDiscord通知"""
    if not os.path.exists(WATCHLIST_FILE): return
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if not watchlist: return

    blocks = []
    for item in watchlist:
        t = item['ticker']
        try:
            df = yf.download(t, period="2d", interval="1m", progress=False)
            c = df['Close'].iloc[:,0]; v = df['Volume'].iloc[:,0]
            ma60, ma200 = c.rolling(60).mean(), c.rolling(200).mean()
            # 法則判定（省略版：主要ロジックのみ）
            is_strong = (ma60.diff(20).iloc[-1] * ma200.diff(20).iloc[-1] > 0)
            if is_strong or (v.iloc[-1] > v.tail(30).mean() * 2.5):
                blocks.append(f"🔹 **{t}** `{c.iloc[-1]:,.1f}円` (予測: {'📈上昇' if is_strong else '🔄反転'})")
        except: continue

    if blocks:
        requests.post(DISCORD_URL, json={"content": "📢 **【定時レポート】**\n" + "\n".join(blocks)})

if __name__ == "__main__":
    now = get_jst_now().time()
    # 09:10 - 09:20 の間なら事前スキャンを実行
    if dt_time(9, 10) <= now <= dt_time(9, 20):
        run_prime_prescan()
    # 監視時間内なら通知サイクルを実行
    elif (dt_time(9, 20) <= now <= dt_time(11, 35)) or (dt_time(12, 35) <= now <= dt_time(15, 15)):
        monitor_cycle()
