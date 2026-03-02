import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime, timedelta, timezone, time as dt_time
import numpy as np

# --- ⚙️ 設定エリア ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

# 監視スケジュール（日本時間）
MONITOR_START = "09:20"
MONITOR_END = "15:10"

# ✅ プライム市場1000銘柄以上のリスト（PRIME_TICKERSとして外部から読み込むか、ここに定義）
# 例: PRIME_TICKERS = ["7203.T", "9984.T", ...] ※各自で用意
try:
    from prime_tickers import PRIME_TICKERS
except ImportError:
    PRIME_TICKERS = ["1605.T", "2502.T", "5401.T", "7203.T", "7267.T", "9020.T", "9432.T", "9433.T"] # テスト用

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def is_market_open():
    now = get_jst_now()
    if now.weekday() >= 5: return False
    curr = now.time()
    return (dt_time(9, 20) <= curr <= dt_time(11, 30)) or (dt_time(12, 40) <= curr <= dt_time(15, 10))

def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

def run_prime_prescan():
    """プライム全件を4分割スキャンして結果を保存"""
    print(f"🚀 事前スキャン開始: {get_jst_now().strftime('%H:%M')}")
    all_t = PRIME_TICKERS
    n = len(all_t)
    chunk = n // 4
    hits = {}
    
    for i in range(4):
        start, end = i*chunk, ((i+1)*chunk if i!=3 else n)
        batch = all_t[start:end]
        try:
            data = yf.download(batch, period="3mo", progress=False)['Close']
            for t in batch:
                c = data[t].dropna()
                if len(c) < 15: continue
                rsi = calculate_rsi(c).tail(5).min()
                if rsi <= 35: hits[t] = f"{rsi:.1f}"
        except: continue
        time.sleep(2)
    
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
    print(f"✅ スキャン完了: {len(hits)}件検知")

def get_prediction_logic(close, volume, ma60, ma200):
    """出来高2.5倍以上 ＋ トレンド傾き予測"""
    s60, s200 = ma60.diff(20).iloc[-1], ma200.diff(20).iloc[-1]
    avg_v = volume.tail(30).mean()
    vol_ratio = (volume.iloc[-1] / avg_v) if avg_v > 0 else 0
    is_spike = vol_ratio >= 2.5
    
    spike_msg = f"🔥 **【出来高急増】{vol_ratio:.1f}倍！**" if is_spike else ""
    if s60 > 0 and s200 > 0: pred = "📈 **上昇強気**: 強い勢いです。"
    elif s60 < 0 and s200 < 0: pred = "📉 **下落継続**: まだ不安定です。"
    else: pred = "🔄 **反転の兆し**: 転換点の可能性があります。"
    return f"{spike_msg}\n{pred}"

def monitor_cycle():
    """5分おきの定時監視とDiscord通知"""
    if not os.path.exists(WATCHLIST_FILE): return
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    
    for item in watchlist:
        t = item['ticker']
        try:
            df = yf.download(t, period="2d", interval="1m", progress=False)
            if df.empty: continue
            c = df['Close'].iloc[:,0]; v = df['Volume'].iloc[:,0]
            ma60, ma200 = c.rolling(60).mean(), c.rolling(200).mean()
            ma20 = c.rolling(20).mean(); std20 = c.rolling(20).std()
            bb_u2, bb_l2 = ma20 + (std20*2), ma20 - (std20*2)
            
            sigs = []
            if c.iloc[-1] > ma60.iloc[-1] and (df['High'].iloc[:,0].tail(15) >= bb_u2.tail(15)).sum() >= 3: sigs.append("法則1: 売り")
            if c.iloc[-1] < ma60.iloc[-1] and (df['Low'].iloc[:,0].tail(15) <= bb_l2.tail(15)).sum() >= 3: sigs.append("法則7: 買い")
            
            msg = f"━━━━━━━━━━━━━━\n📢 **【Jack株AI：定時予測】**\n銘柄: **{t}**\n"
            msg += f"値: `{c.iloc[-1]:,.1f}円` ({get_jst_now().strftime('%H:%M')})\n"
            msg += f"🕙 監視: {MONITOR_START}-{MONITOR_END}\n"
            if sigs: msg += "\n".join([f"⚠️ {s}" for s in sigs]) + "\n"
            msg += f"\n{get_prediction_logic(c, v, ma60, ma200)}\n━━━━━━━━━━━━━━"
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
        except: continue

if __name__ == "__main__":
    last_scan_date = ""
    print(f"🚀 バックグラウンド監視開始 (日本時間)")
    while True:
        now = get_jst_now()
        # 09:15 自動スキャン
        if now.time() >= dt_time(9, 15) and last_scan_date != now.strftime('%Y-%m-%d'):
            run_prime_prescan()
            last_scan_date = now.strftime('%Y-%m-%d')
        
        # 09:20以降 市場が開いていれば5分おき監視
        if is_market_open():
            monitor_cycle()
            time.sleep(300)
        else:
            time.sleep(60)
