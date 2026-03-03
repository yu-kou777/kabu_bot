import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import numpy as np
from datetime import datetime, timedelta, timezone

# --- ⚙️ 基本設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

TICKER_NAMES = {
    "2502.T": "アサヒ", "5401.T": "日本製鉄", "7267.T": "ホンダ",
    "9020.T": "JR東日本", "9432.T": "NTT", "9433.T": "KDDI"
}
PRIME_TICKERS = list(TICKER_NAMES.keys()) + ["1605.T", "7203.T", "8035.T", "9984.T"]

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# --- 📈 テクニカル計算関数 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def calculate_rci(series, period=9):
    def rci_func(x):
        n = len(x)
        d = np.array(range(n, 0, -1))
        r = pd.Series(x).rank(method='min').values
        return (1 - 6 * sum((d - r)**2) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- 📡 1. 日足スキャン ---
def run_daily_scan():
    print(f"🚀 【テスト】日足スキャン開始: {get_jst_now()}")
    hits = {}
    try:
        data = yf.download(PRIME_TICKERS, period="1y", progress=False)
        close_df = data['Close']
        vol_df = data['Volume']

        for t in PRIME_TICKERS:
            c = close_df[t].dropna()
            v = vol_df[t].dropna()
            if len(c) < 30: continue
            rsi = calculate_rsi(c, 14).iloc[-1]
            rci = calculate_rci(c, 9).iloc[-1]
            hits[t] = f"テスト検知 (RSI:{rsi:.0f}/RCI:{rci:.0f})"
            print(f"✅ スキャン検知: {t}")
    except Exception as e:
        print(f"❌ スキャンエラー: {e}")
    
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)

# --- 🔔 2. 監視通知 ---
def monitor_cycle():
    print(f"🔔 【テスト】監視サイクル開始: {get_jst_now()}")
    # テスト時は監視リストがなくても主要銘柄をチェック
    target_list = []
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            target_list = json.load(f)
    
    if not target_list:
        target_list = [{"ticker": t} for t in TICKER_NAMES.keys()]

    report_blocks = []
    for item in target_list:
        t = item['ticker']
        try:
            df = yf.download(t, period="2d", interval="1m", progress=False)
            c = df['Close'].iloc[:,0]; v = df['Volume'].iloc[:,0]
            ma60 = c.rolling(60).mean()
            now_p = c.iloc[-1]
            report_blocks.append(f"🔹**{TICKER_NAMES.get(t, t)}** `{now_p:,.1f}` | テスト通知成功 ✅")
        except: continue

    if report_blocks:
        msg = f"🧪 **【Jack株AI：動作テスト中】**\n" + "\n".join(report_blocks)
        requests.post(DISCORD_URL, json={"content": msg})

if __name__ == "__main__":
    # 時間制限なしで強制実行
    run_daily_scan()
    monitor_cycle()

