import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import io
import numpy as np
from datetime import datetime, timedelta, timezone, time as dt_time

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
PRE_SCAN_FILE = "pre_scan_results.json"
WATCHLIST_FILE = "jack_watchlist.json"
JPX_LIST_URL = "https://www.jpx.co.jp/markets/statistics-banner/quote/tvdivq0000001vg2-att/data_j.xls"

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_discord(msg):
    try: requests.post(DISCORD_URL, json={"content": msg}, timeout=10)
    except: print(f"Discord送信失敗: {msg}")

# --- 📈 テクニカル計算 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def calculate_rci(series, period=9):
    def rci_func(x):
        n = len(x); d = np.array(range(n, 0, -1)); r = pd.Series(x).rank(method='min').values
        return (1 - 6 * sum((d - r)**2) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- 📡 1. 高速日足全件スキャン ---
def run_full_daily_scan():
    print("🚀 全件スキャンを開始します...")
    send_discord("🔍 **【Jack株AI】プライム市場全件スキャンを開始します...**")
    try:
        res = requests.get(JPX_LIST_URL)
        # 💡 FutureWarning対策：BytesIOでラップ
        df = pd.read_excel(io.BytesIO(res.content))
        prime_df = df[df['市場・商品区分'].str.contains('プライム', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
        tickers = list(name_map.keys())
    except Exception as e:
        send_discord(f"❌ 銘柄リスト取得失敗: {e}"); return

    hits = {}
    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i : i + chunk_size]
        try:
            data = yf.download(batch, period="1mo", progress=False)['Close']
            for t in batch:
                if t not in data or data[t].isnull().all(): continue
                c = data[t].dropna()
                if len(c) < 20: continue
                rsi = calculate_rsi(c, 14).iloc[-1]; rci = calculate_rci(c, 9).iloc[-1]
                if (rsi <= 20 and rci <= -70) or (rsi >= 90 and rci >= 95):
                    status = "📉 底圏" if rsi <= 20 else "📈 天井"
                    hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f}/RCI:{rci:.0f})"}
        except: continue
        time.sleep(1)
        if i % 500 == 0: print(f"📊 スキャン中... {i}/{len(tickers)}")

    # 結果を保存
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f, ensure_ascii=False)
    send_discord(f"✨ **【スキャン完了】** お宝候補は **{len(hits)}件** です。Streamlitを確認してください。")

if __name__ == "__main__":
    now_jst = get_jst_now()
    now_t = now_jst.time()
    today_str = now_jst.strftime('%Y-%m-%d')
    
    # 既存のファイル日付を確認
    last_date = ""
    if os.path.exists(PRE_SCAN_FILE):
        with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
            last_date = json.load(f).get('date', "")

    # ✅ 修正：日付が今日でなければ、時間に関係なくスキャンを実行する！
    if (last_date != today_str) or (dt_time(8, 45) <= now_t <= dt_time(9, 30)):
        run_full_daily_scan()
