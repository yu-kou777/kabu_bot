import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import numpy as np
from datetime import datetime, timedelta, timezone

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
PRE_SCAN_FILE = "pre_scan_results.json"
WATCHLIST_FILE = "jack_watchlist.json"

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_discord(msg):
    try: requests.post(DISCORD_URL, json={"content": msg}, timeout=10)
    except: print(f"Discord送信失敗")

def calculate_rsi(series, period=14):
    if len(series) < period: return pd.Series([np.nan]*len(series))
    delta = series.diff(); gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- 📡 銘柄リスト（JPXブロック回避のため主要銘柄を内蔵） ---
def get_target_tickers():
    # 💡 ここに監視したい主要銘柄を追加。JPXから取得せず直接指定することで確実に動く
    base_map = {
        "7203.T":"トヨタ", "9432.T":"NTT", "9984.T":"SBG", "6758.T":"ソニーG", "8306.T":"三菱UFJ",
        "8035.T":"東エレク", "6098.T":"リクルート", "4502.T":"武田", "2502.T":"アサヒ", "5401.T":"日本製鉄",
        "7267.T":"ホンダ", "9020.T":"JR東日本", "9433.T":"KDDI", "4063.T":"信越化", "6501.T":"日立",
        "6954.T":"ファナック", "4519.T":"中外薬", "6273.T":"SMC", "6367.T":"ダイキン", "3382.T":"セブン&アイ"
        # 必要に応じて追加してください。
    }
    return base_map

def run_scan():
    send_discord("🔍 **【Jack株AI】高速バッチスキャンを開始します...**")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    hits = {}
    
    # 💡 50銘柄ずつの塊で一気に取得して時間を短縮
    chunk_size = 50
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i : i + chunk_size]
        try:
            data = yf.download(batch, period="1mo", progress=False, threads=False)['Close']
            for t in batch:
                if t not in data or data[t].isnull().all(): continue
                c = data[t].dropna()
                if len(c) < 15: continue
                rsi = calculate_rsi(c, 14).iloc[-1]
                
                # RSI 25以下 または 75以上
                if not np.isnan(rsi) and (rsi <= 25 or rsi >= 75):
                    status = "📉 底圏" if rsi <= 25 else "📈 天井"
                    hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f})"}
        except: continue
        time.sleep(5) # 休憩
    
    # 強制保存
    result = {"date": get_jst_now().strftime('%Y-%m-%d %H:%M'), "hits": hits}
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    send_discord(f"✨ **【スキャン完了】** 候補：{len(hits)}件")

if __name__ == "__main__":
    run_scan()
