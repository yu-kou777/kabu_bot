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
JPX_LIST_URL = "https://www.jpx.co.jp/markets/statistics-banner/quote/tvdivq0000001vg2-att/data_j.xls"

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_discord(msg):
    try: requests.post(DISCORD_URL, json={"content": msg}, timeout=10)
    except: print("Discord送信失敗")

# --- 📈 テクニカル計算 ---
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

# --- 📡 1. 日足全件スキャン ---
def run_full_daily_scan():
    send_discord("🔍 **【Jack株AI】プライム市場 1,600銘柄の全件スキャンを開始します...**")
    try:
        res = requests.get(JPX_LIST_URL)
        df = pd.read_excel(res.content)
        prime_df = df[df['市場・商品区分'].str.contains('プライム', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
        tickers = list(name_map.keys())
    except Exception as e:
        send_discord(f"❌ 銘柄リスト取得失敗: {e}"); return

    hits = {}
    chunk_size = 50 
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i : i + chunk_size]
        try:
            data = yf.download(batch, period="1y", progress=False)['Close']
            for t in batch:
                if t not in data or data[t].isnull().all(): continue
                c = data[t].dropna()
                if len(c) < 30: continue
                rsi = calculate_rsi(c, 14).iloc[-1]
                rci = calculate_rci(c, 9).iloc[-1]
                
                # 極値判定
                if (rsi <= 20 and rci <= -70) or (rsi >= 90 and rci >= 95):
                    status = "📉 底圏" if rsi <= 20 else "📈 天井"
                    hits[t] = {"name": name_map.get(t, t), "reason": f"{status}(RSI:{rsi:.0f}/RCI:{rci:.0f})"}
        except: continue
        time.sleep(1)

    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f, ensure_ascii=False)
    send_discord(f"✨ **【スキャン完了】** お宝候補は **{len(hits)}件** です。Streamlitを確認してください。")

# --- 🔔 2. 1分足リアルタイム監視 ---
def monitor_cycle():
    if not os.path.exists(WATCHLIST_FILE): return
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if not watchlist: return

    report_blocks = []
    for item in watchlist:
        t = item['ticker']
        name = item.get('name', t)
        try:
            df = yf.download(t, period="2d", interval="1m", progress=False)
            c = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
            ma60, ma200 = c.rolling(60).mean(), c.rolling(200).mean()
            ma20 = c.rolling(20).mean(); std20 = c.rolling(20).std()
            bb_u2, bb_l2, bb_l3 = ma20 + std20*2, ma20 - std20*2, ma20 - std20*3
            
            now_p = float(c.iloc[-1]); m60 = ma60.iloc[-1]; m200 = ma200.iloc[-1]
            sigs = []
            if now_p > m60:
                if (df['High'].iloc[:,0].tail(15) >= bb_u2.tail(15)).sum() >= 3: sigs.append("⚠️法則1(売)")
                if abs(now_p - m60) / m60 < 0.001: sigs.append("💎法則2(買)")
            else:
                if now_p <= bb_l3.iloc[-1]: sigs.append("⚠️法則4(買)")
                if abs(now_p - m200) / m200 < 0.001: sigs.append("💎法則5(買)")
                if (df['Low'].iloc[:,0].tail(15) <= bb_l2.tail(15)).sum() >= 3: sigs.append("⚠️法則7(買)")
            
            if sigs:
                report_blocks.append(f"🔹**{name}**({t}) `{now_p:,.1f}円` | {' '.join(sigs)}")
        except: continue

    if report_blocks:
        send_discord(f"📢 **【Jack株AI：アルゴ検知】**\n" + "\n".join(report_blocks))

if __name__ == "__main__":
    now = get_jst_now().time()
    # 08:45にスキャン。ファイルがない場合も実行
    if (dt_time(8, 45) <= now <= dt_time(9, 30)) or not os.path.exists(PRE_SCAN_FILE):
        run_full_daily_scan()
    
    # 挨拶通知
    if dt_time(9, 0) <= now <= dt_time(9, 5): send_discord("🌅 **【前場】監視を開始しました。**")
    if dt_time(15, 10) <= now <= dt_time(15, 15): send_discord("🏁 **【大引け】本日の監視を終了しました。**")

    # 取引時間中のみ監視実行（自動停止）
    if (dt_time(9, 0) <= now <= dt_time(11, 35)) or (dt_time(12, 35) <= now <= dt_time(15, 15)):
        monitor_cycle()
