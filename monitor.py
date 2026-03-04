import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import io
import numpy as np
from datetime import datetime, timedelta, timezone

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
PRE_SCAN_FILE = "pre_scan_results.json"
WATCHLIST_FILE = "jack_watchlist.json"
JPX_LIST_URL = "https://www.jpx.co.jp/markets/statistics-banner/quote/tvdivq0000001vg2-att/data_j.xls"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_discord(msg):
    try: requests.post(DISCORD_URL, json={"content": msg}, timeout=10)
    except: print(f"Discord送信失敗: {msg}")

def calculate_rsi(series, period=14):
    if len(series) < period: return pd.Series([np.nan]*len(series))
    delta = series.diff(); gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- 📡 600銘柄バッチ・高速スキャン ---
def run_batch_scan():
    print("🚀 600銘柄バッチ・スキャンを開始します...")
    send_discord("🔍 **【Jack株AI】600銘柄バッチ・スキャンを即時実行します...**")
    
    name_map = {}
    try:
        res = requests.get(JPX_LIST_URL, headers=HEADERS, timeout=30)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘銘名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        print(f"JPX Error: {e}")
        send_discord(f"⚠️ リスト取得失敗: {e}"); return

    tickers = list(name_map.keys())
    hits = {}
    batch_size = 600 # 💡 600銘柄ずつまとめて取得
    
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        print(f"📦 バッチ取得中: {i+1}〜{min(i+batch_size, len(tickers))} 銘柄")
        
        try:
            # 高速化のため期間を1moに絞り、threads=Falseでお行儀よく取得
            data = yf.download(batch, period="1mo", progress=False, threads=False)
            close_data = data['Close']
            
            for t in batch:
                try:
                    c = close_data[t].dropna() if isinstance(close_data, pd.DataFrame) else close_data.dropna()
                    if len(c) < 15: continue
                    rsi = calculate_rsi(c, 14).iloc[-1]
                    
                    # お宝条件：RSI 30以下 または 70以上
                    if not np.isnan(rsi) and (rsi <= 30 or rsi >= 70):
                        status = "📉 底圏" if rsi <= 30 else "📈 天井"
                        hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f})"}
                except: continue
        except Exception as e:
            print(f"Batch Error: {e}")
        
        time.sleep(10) # バッチ間のインターバル（Yahoo対策）

    # 常に新しい日付で保存
    result_data = {"date": get_jst_now().strftime('%Y-%m-%d %H:%M'), "hits": hits}
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    send_discord(f"✨ **【スキャン完了】** 候補銘柄は **{len(hits)}件** です。")

if __name__ == "__main__":
    # 💡 時刻判定をなくし、実行されたら必ずスキャンするようにしました
    run_batch_scan()
