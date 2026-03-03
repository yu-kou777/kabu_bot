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

TICKER_NAMES = {
    "2502.T": "アサヒ", "5401.T": "日本製鉄", "7267.T": "ホンダ",
    "9020.T": "JR東日本", "9432.T": "NTT", "9433.T": "KDDI"
}
PRIME_TICKERS = list(TICKER_NAMES.keys()) + ["1605.T", "1801.T", "7203.T", "9984.T"]

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
            # 💡 判定しきい値を調整（テスト用）
            if rsi <= 50: hits[t] = f"RSI:{rsi:.1f}"
    except Exception as e:
        print(f"❌ スキャンエラー: {e}")
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
    print(f"🏁 スキャン完了：{len(hits)}件検知")

def monitor_cycle():
    if not os.path.exists(WATCHLIST_FILE): return
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if not watchlist: return

    report_blocks = []
    for item in watchlist:
        t = item['ticker']
        name = TICKER_NAMES.get(t, t)
        try:
            df = yf.download(t, period="2d", interval="1m", progress=False)
            c = df['Close'].iloc[:,0]; v = df['Volume'].iloc[:,0]
            ma60, ma200 = c.rolling(60).mean(), c.rolling(200).mean()
            ma20 = c.rolling(20).mean(); std20 = c.rolling(20).std()
            bb_u2, bb_l2 = ma20 + (std20*2), ma20 - (std20*2)

            now_p = c.iloc[-1]
            sigs = []
            if now_p > ma60.iloc[-1] and (df['High'].iloc[:,0].tail(15) >= bb_u2.tail(15)).sum() >= 3: sigs.append("⚠️法則1(天)")
            if now_p < ma60.iloc[-1] and (df['Low'].iloc[:,0].tail(15) <= bb_l2.tail(15)).sum() >= 3: sigs.append("⚠️法則7(底)")
            
            is_strong = (ma60.diff(20).iloc[-1] * ma200.diff(20).iloc[-1] > 0)
            avg_v = v.tail(30).mean()
            is_spike = (v.iloc[-1] > avg_v * 2.5) if avg_v > 0 else False

            if sigs or is_strong or is_spike:
                pred = "📈上昇" if is_strong else "🔄反転"
                block = f"🔹**{name}**({t}) `{now_p:,.1f}` | {' '.join(sigs)} {'💎法則8' if is_strong else ''} {'🔥Vol急増' if is_spike else ''} 予測:{pred}"
                report_blocks.append(block)
        except: continue

    if report_blocks:
        msg = f"📢 **【Jack株AI：チャンス到来】** ({get_jst_now().strftime('%H:%M')})\n" + "\n".join(report_blocks)
        requests.post(DISCORD_URL, json={"content": msg})

if __name__ == "__main__":
    now_t = get_jst_now().time()
    # ファイルがない、または朝の時間はスキャン
    if not os.path.exists(PRE_SCAN_FILE) or (dt_time(9, 10) <= now_t <= dt_time(9, 25)):
        run_prime_prescan()
    
    # 取引時間中なら監視を実行
    if (dt_time(9, 20) <= now_t <= dt_time(11, 35)) or (dt_time(12, 35) <= now_t <= dt_time(15, 15)):
        monitor_cycle()
