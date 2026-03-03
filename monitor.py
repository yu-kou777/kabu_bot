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

# --- 📈 テクニカル計算 ---
def calculate_rsi(series, period=14):
    delta = series.diff(); gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def calculate_rci(series, period=9):
    def rci_func(x):
        n = len(x); d = np.array(range(n, 0, -1)); r = pd.Series(x).rank(method='min').values
        return (1 - 6 * sum((d - r)**2) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- 📡 1. 早朝の日足全件スキャン ---
def run_full_daily_scan():
    print("🌐 JPXから最新の和名リストを取得中...")
    try:
        res = requests.get(JPX_LIST_URL)
        df = pd.read_excel(res.content)
        prime_df = df[df['市場・商品区分'].str.contains('プライム', na=False)]
        # 和名辞書を作成 { "9432.T": "日本電信電話", ... }
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
        tickers = list(name_map.keys())
    except Exception as e:
        print(f"❌ リスト取得失敗: {e}"); return

    hits = {}
    chunk_size = 50 
    print(f"📡 全件スキャン開始（1,600銘柄）: {get_jst_now()}")
    
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i : i + chunk_size]
        try:
            data = yf.download(batch, period="1y", progress=False)['Close']
            for t in batch:
                if t not in data or data[t].isnull().all(): continue
                c = data[t].dropna()
                if len(c) < 30: continue
                rsi = calculate_rsi(c, 14).iloc[-1]; rci = calculate_rci(c, 9).iloc[-1]
                
                # ✅ 極値検知
                if (rsi <= 20 and rci <= -70) or (rsi >= 90 and rci >= 95):
                    status = "📉 底圏" if rsi <= 20 else "📈 天井"
                    # 名前を辞書から取得して保存
                    hits[t] = {
                        "name": name_map.get(t, t),
                        "reason": f"{status}(RSI:{rsi:.0f}/RCI:{rci:.0f})"
                    }
        except: continue
        time.sleep(1)
        if i % 300 == 0: print(f"📊 スキャン進捗: {i}/{len(tickers)}...")

    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f, ensure_ascii=False)
    
    requests.post(DISCORD_URL, json={"content": f"✅ **【Jack株AI】全件スキャン完了**\n本日のお宝候補は **{len(hits)}件** です。"})

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
            if m200 > m60 and abs(now_p - m200) / m200 < 0.001: sigs.append("⚠️法則3(売)")
            
            is_strong = (ma60.diff(5).iloc[-1] * ma200.diff(5).iloc[-1] > 0)
            if sigs or is_strong:
                report_blocks.append(f"🔹**{name}**({t}) `{now_p:,.1f}円` | {' '.join(sigs)} {'💎法則8' if is_strong else ''}")
        except: continue

    if report_blocks:
        msg = f"📢 **【Jack株AI：アルゴ検知】** ({get_jst_now().strftime('%H:%M')})\n" + "\n".join(report_blocks)
        requests.post(DISCORD_URL, json={"content": msg})

if __name__ == "__main__":
    now = get_jst_now().time()
    if (dt_time(8, 45) <= now <= dt_time(9, 30)) or not os.path.exists(PRE_SCAN_FILE):
        run_full_daily_scan()
    if (dt_time(9, 0) <= now <= dt_time(11, 35)) or (dt_time(12, 35) <= now <= dt_time(15, 15)):
        monitor_cycle()

