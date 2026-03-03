import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import numpy as np
from datetime import datetime, timedelta, timezone, time as dt_time

# --- ⚙️ 基本設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

# 監視銘柄（和名）
TICKER_NAMES = {
    "2502.T": "アサヒ", "5401.T": "日本製鉄", "7267.T": "ホンダ",
    "9020.T": "JR東日本", "9432.T": "NTT", "9433.T": "KDDI"
}
# プライム主要銘柄（全1600件に拡張可能）
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

# --- 📡 1. 朝の「日足お宝スキャン」 ---
def run_daily_scan():
    print(f"📡 日足スキャン開始: {get_jst_now()}")
    hits = {}
    try:
        data = yf.download(PRIME_TICKERS, period="1y", progress=False)
        close_df = data['Close']
        vol_df = data['Volume']

        for t in PRIME_TICKERS:
            c = close_df[t].dropna()
            v = vol_df[t].dropna()
            if len(c) < 30: continue

            # 指標計算
            rsi = calculate_rsi(c, 14).iloc[-1]
            rci = calculate_rci(c, 9).iloc[-1]
            avg_vol = v.tail(30).mean()
            vol_ratio = v.iloc[-1] / avg_vol if avg_vol > 0 else 0

            # ✅ 条件1：RSI(90+) & RCI(95+) または RSI(20-) & RCI(-70-)
            if (rsi >= 90 and rci >= 95) or (rsi <= 20 and rci <= -70):
                hits[t] = f"極値検知 (RSI:{rsi:.0f}/RCI:{rci:.0f})"
            
            # ✅ 条件2：出来高急増 かつ RSI(30- or 70+)
            elif vol_ratio >= 2.0 and (rsi <= 30 or rsi >= 70):
                hits[t] = f"出来高伴う節目 (RSI:{rsi:.0f}/Vol:{vol_ratio:.1f}倍)"

    except Exception as e:
        print(f"スキャンエラー: {e}")
    
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
    print(f"🏁 スキャン完了: {len(hits)}件検知")

# --- 🔔 2. 日中の「1分足リアルタイム監視」 ---
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
            c = df['Close'].iloc[:,0]; v = df['Volume'].iloc[:,0]
            ma60, ma200 = c.rolling(60).mean(), c.rolling(200).mean()
            ma20 = c.rolling(20).mean(); std20 = c.rolling(20).std()
            bb_u2, bb_l2, bb_l3 = ma20 + std20*2, ma20 - std20*2, ma20 - std20*3

            now_p = c.iloc[-1]
            m60, m200 = ma60.iloc[-1], ma200.iloc[-1]
            sigs = []

            # ✅ 画像の8ルール実装
            if now_p > m60:
                if (df['High'].iloc[:,0].tail(15) >= bb_u2.tail(15)).sum() >= 3: sigs.append("⚠️ルール1(天売)")
                if abs(now_p - m60) / m60 < 0.001: sigs.append("💎ルール2(60線反発買)")
            else: # now_p < m60
                if now_p <= bb_l3.iloc[-1]: sigs.append("⚠️ルール4(-3σ接触買)")
                if abs(now_p - m200) / m200 < 0.001: sigs.append("💎ルール5(200線反発買)")
                if (df['Low'].iloc[:,0].tail(15) <= bb_l2.tail(15)).sum() >= 3: sigs.append("⚠️ルール7(-2σ×3接触買)")

            if m200 > m60 and abs(now_p - m200) / m200 < 0.001: sigs.append("⚠️ルール3(200線接触売)")
            
            # 強さ判定（MA方向）
            slope60, slope200 = ma60.diff(5).iloc[-1], ma200.diff(5).iloc[-1]
            is_strong = (slope60 * slope200 > 0)
            
            if sigs or is_strong:
                msg = f"🔹**{TICKER_NAMES.get(t, t)}** `{now_p:,.1f}` | {' '.join(sigs)} {'🔥強トレンド' if is_strong else ''}"
                report_blocks.append(msg)
        except: continue

    if report_blocks:
        requests.post(DISCORD_URL, json={"content": f"📢 **【Jack株AI：アルゴ検知】**\n" + "\n".join(report_blocks)})

if __name__ == "__main__":
    now_t = get_jst_now().time()
    # 朝の時間は日足スキャン
    if not os.path.exists(PRE_SCAN_FILE) or (dt_time(9, 10) <= now_t <= dt_time(9, 25)):
        run_daily_scan()
    # 取引時間は1分足監視
    if (dt_time(9, 20) <= now_t <= dt_time(11, 35)) or (dt_time(12, 35) <= now_t <= dt_time(15, 15)):
        monitor_cycle()
