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
    if len(series) < period: return pd.Series([np.nan] * len(series))
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
    send_discord("🔍 **【Jack株AI】全件スキャンを開始します（JPXデータ取得中）...**")
    
    name_map = {}
    try:
        res = requests.get(JPX_LIST_URL, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content))
        # 「プライム」または「Prime」を含む行を抽出
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        send_discord(f"⚠️ JPXリスト取得に失敗しました。主要銘柄で代替します。({e})")
        # バックアップ用リスト
        name_map = {"7203.T":"トヨタ", "9432.T":"NTT", "9984.T":"ソフトバンクG", "6758.T":"ソニーG", "8306.T":"三菱UFJ"}

    tickers = list(name_map.keys())
    hits = {}
    chunk_size = 50 # 確実性を高めるため50件ずつ
    
    if not tickers:
        send_discord("❌ スキャン対象の銘柄が見つかりませんでした。")
        return

    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i : i + chunk_size]
        try:
            data = yf.download(batch, period="1mo", progress=False)['Close']
            for t in batch:
                if t not in data or data[t].isnull().all(): continue
                c = data[t].dropna()
                if len(c) < 15: continue
                
                rsi = calculate_rsi(c, 14).iloc[-1]
                rci = calculate_rci(c, 9).iloc[-1]
                
                # RSI 20以下 または 90以上（RCIとの複合判定）
                if (not np.isnan(rsi)) and (not np.isnan(rci)):
                    if (rsi <= 20 and rci <= -70) or (rsi >= 90 and rci >= 95):
                        status = "📉 底圏" if rsi <= 20 else "📈 天井"
                        hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f}/RCI:{rci:.0f})"}
        except Exception as e:
            print(f"Batch Error: {e}")
        time.sleep(1)

    # ✅ 成果物を必ず保存する
    result_data = {"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    send_discord(f"✨ **【スキャン完了】** お宝候補は **{len(hits)}件** です。Streamlitを更新してください。")

if __name__ == "__main__":
    now_jst = get_jst_now()
    now_t = now_jst.time()
    
    # 常に最新を取りたいので、ファイルがあっても日付が違えば実行
    run_full_daily_scan()
