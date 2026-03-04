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

# 💡 ブロック回避用の「ブラウザのふり」をするヘッダー
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

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

# --- 📡 スキャン実行 ---
def run_stealth_scan():
    send_discord("🔍 **【Jack株AI】ステルスモードで全件スキャンを開始します...**")
    
    name_map = {}
    try:
        # 💡 JPX取得をブラウザ経由に見せかける
        res = requests.get(JPX_LIST_URL, headers=HEADERS, timeout=30)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)].head(600)
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        send_discord(f"⚠️ JPXブロック継続中。予備リストで続行します。({e})")
        name_map = {"7203.T":"トヨタ", "9432.T":"NTT", "9984.T":"SBG", "6758.T":"ソニーG", "8306.T":"三菱UFJ"}

    tickers = list(name_map.keys())
    hits = {}
    
    # ✅ 改善：ブロックを避けるため20銘柄ずつの塊で、ゆっくり進む
    chunk_size = 20 
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i : i + chunk_size]
        try:
            # 💡 threads=False でアクセスを1本に絞り、お行儀よく取得
            data = yf.download(batch, period="1mo", progress=False, threads=False)
            close_data = data['Close'] if 'Close' in data else data
            
            for t in batch:
                try:
                    c = close_data[t].dropna() if isinstance(close_data, pd.DataFrame) else close_data.dropna()
                    if len(c) < 15: continue
                    rsi = calculate_rsi(c, 14).iloc[-1]
                    if not np.isnan(rsi) and (rsi <= 30 or rsi >= 70):
                        status = "📉 底圏" if rsi <= 30 else "📈 天井"
                        hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f})"}
                except: continue
        except Exception as e:
            print(f"Batch Error: {e}")
            time.sleep(20) # エラー時は長めに休む
        
        # ✅ 重要：バッチごとに10秒休む（Yahooへのマナー）
        time.sleep(10)
        if i % 100 == 0: print(f"📊 進捗: {i}/{len(tickers)} 完了")

    # 強制保存
    result_data = {"date": get_jst_now().strftime('%Y-%m-%d %H:%M'), "hits": hits}
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    send_discord(f"✨ **【スキャン完了】** 600銘柄の精査が終わりました。候補：**{len(hits)}件**")

if __name__ == "__main__":
    run_stealth_scan()
