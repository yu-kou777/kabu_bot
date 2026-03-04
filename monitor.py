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

# --- 📋 銘柄リスト取得（ガード強化） ---
def get_tickers():
    name_map = {}
    try:
        res = requests.get(JPX_LIST_URL, headers=HEADERS, timeout=30)
        # HTMLが返ってきたらエラーとして扱う
        if res.content.startswith(b'<!DOCTYP'):
            raise ValueError("JPXサイトにブロックされました。")
        
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        print(f"JPX Error: {e}")
        send_discord(f"⚠️ JPXリスト取得失敗のため、主要銘柄でスキャンします。({e})")
        # ⚠️ バックアップ用主要15銘柄
        name_map = {
            "7203.T":"トヨタ", "9432.T":"NTT", "9984.T":"SBG", "6758.T":"ソニーG", "8306.T":"三菱UFJ",
            "8035.T":"東エレク", "6098.T":"リクルート", "4502.T":"武田", "2502.T":"アサヒ", "5401.T":"日本製鉄",
            "7267.T":"ホンダ", "9020.T":"JR東日本", "9433.T":"KDDI", "4063.T":"信越化", "6501.T":"日立"
        }
    return name_map

# --- 📡 実行エンジン ---
def run_batch_scan():
    send_discord("🔍 **【Jack株AI】600銘柄バッチ・高速スキャンを開始します...**")
    name_map = get_tickers()
    tickers = list(name_map.keys())
    hits = {}
    
    # ✅ 600銘柄ずつの塊で一気に取得して時間を短縮
    batch_size = 600
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        print(f"📦 バッチ処理中: {i+1}〜{min(i+batch_size, len(tickers))} 銘柄")
        
        try:
            # 💡 期間を1mo、threads=Falseでアクセスを1本に絞り、お行儀よく取得
            data = yf.download(batch, period="1mo", interval="1d", progress=False, threads=False)
            close_data = data['Close'] if 'Close' in data else data
            
            for t in batch:
                try:
                    if isinstance(close_data, pd.DataFrame):
                        if t not in close_data: continue
                        c = close_data[t].dropna()
                    else:
                        c = close_data.dropna()
                        
                    if len(c) < 15: continue
                    rsi = calculate_rsi(c, 14).iloc[-1]
                    
                    # お宝条件：RSI 25以下 または 80以上
                    if not np.isnan(rsi) and (rsi <= 25 or rsi >= 80):
                        status = "📉 底圏" if rsi <= 25 else "📈 天井"
                        hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f})"}
                except: continue
        except Exception as e:
            print(f"Batch Error: {e}")
        
        time.sleep(15) # バッチ間の休憩（Yahooの制限回避）

    # ✅ 常にファイルを書き込んでgit commitを発生させる
    result_data = {
        "date": get_jst_now().strftime('%Y-%m-%d %H:%M'),
        "hits": hits
    }
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    send_discord(f"✨ **【スキャン完了】** 処理が完了しました。候補：**{len(hits)}件**")

if __name__ == "__main__":
    run_batch_scan()
