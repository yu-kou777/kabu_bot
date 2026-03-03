import yfinance as yf
import pandas as pd
import requests
import json
import os
import numpy as np
from datetime import datetime, timedelta, timezone, time as dt_time

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

TICKER_NAMES = {
    "2502.T": "アサヒ", "5401.T": "日本製鉄", "7267.T": "ホンダ",
    "9020.T": "JR東日本", "9432.T": "NTT", "9433.T": "KDDI"
}
PRIME_TICKERS = list(TICKER_NAMES.keys()) + ["1605.T", "7203.T", "8035.T", "9984.T", "8306.T", "8001.T", "4063.T"]

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# --- 📈 テクニカル指標 ---
def calculate_rsi(series, period=14):
    delta = series.diff(); gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def calculate_rci(series, period=9):
    def rci_func(x):
        n = len(x); d = np.array(range(n, 0, -1)); r = pd.Series(x).rank(method='min').values
        return (1 - 6 * sum((d - r)**2) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- 📡 1. 朝の日足スキャン（9:10-9:25） ---
def run_daily_scan():
    print(f"📡 日足スキャン開始: {get_jst_now()}")
    hits = {}
    try:
        data = yf.download(PRIME_TICKERS, period="1y", progress=False)['Close']
        for t in PRIME_TICKERS:
            c = data[t].dropna()
            if len(c) < 30: continue
            rsi = calculate_rsi(c, 14).iloc[-1]; rci = calculate_rci(c, 9).iloc[-1]
            if (rsi >= 90 and rci >= 95) or (rsi <= 20 and rci <= -70):
                hits[t] = f"極値(RSI:{rsi:.0f}/RCI:{rci:.0f})"
        with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
            json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
        print(f"✅ スキャン完了")
    except Exception as e: print(f"❌ エラー: {e}")

# --- 🔔 2. 1分足リアルタイム監視（市場稼働中） ---
def monitor_cycle():
    if not os.path.exists(WATCHLIST_FILE): return
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if not watchlist: return

    report_blocks = []
    for item in watchlist:
        t = item['ticker']
        try:
            df = yf.download(t, period="2d", interval="1m", progress=False)
            c = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
            ma60, ma200 = c.rolling(60).mean(), c.rolling(200).mean()
            ma20 = c.rolling(20).mean(); std20 = c.rolling(20).std()
            bb_u2, bb_l2, bb_l3 = ma20 + std20*2, ma20 - std20*2, ma20 - std20*3
            now_p = float(c.iloc[-1]); m60 = ma60.iloc[-1]; m200 = ma200.iloc[-1]
            
            sigs = []
            # ✅ ジャックさんの8ルール実装
            if now_p > m60:
                if (df['High'].iloc[:,0].tail(15) >= bb_u2.tail(15)).sum() >= 3: sigs.append("⚠️法則1(売)")
                if abs(now_p - m60) / m60 < 0.001: sigs.append("💎法則2(買)")
            else:
                if now_p <= bb_l3.iloc[-1]: sigs.append("⚠️法則4(買)")
                if abs(now_p - m200) / m200 < 0.001: sigs.append("💎法則5(買)")
                if (df['Low'].iloc[:,0].tail(15) <= bb_l2.tail(15)).sum() >= 3: sigs.append("⚠️法則7(買)")
            
            if m200 > m60 and abs(now_p - m200) / m200 < 0.001: sigs.append("⚠️法則3(売)")
            
            # 法則8：同じ方向なら強い
            is_strong = (ma60.diff(5).iloc[-1] * ma200.diff(5).iloc[-1] > 0)
            
            if sigs or is_strong:
                name = TICKER_NAMES.get(t, t)
                report_blocks.append(f"🔹**{name}**({t}) `{now_p:,.1f}` | {' '.join(sigs)} {'💎法則8' if is_strong else ''}")
        except: continue

    if report_blocks:
        msg = f"📢 **【Jack株AI：アルゴ検知】** ({get_jst_now().strftime('%H:%M')})\n" + "\n".join(report_blocks)
        requests.post(DISCORD_URL, json={"content": msg})

if __name__ == "__main__":
    now = get_jst_now().time()
    # 朝のスキャン時間（またはファイルがない場合）
    if (dt_time(9, 10) <= now <= dt_time(9, 25)) or not os.path.exists(PRE_SCAN_FILE):
        run_daily_scan()
    # 市場時間中のみ監視
    if (dt_time(9, 20) <= now <= dt_time(11, 35)) or (dt_time(12, 35) <= now <= dt_time(15, 15)):
        monitor_cycle()
