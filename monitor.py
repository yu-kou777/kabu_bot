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

# --- 📈 RSI計算ロジック ---
def calculate_rsi(series, period=14):
    if len(series) < period: return pd.Series([np.nan]*len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 📋 ターゲット銘柄 (主要600銘柄への道：まずは代表的なものを定義) ---
def get_prime_600_list():
    # 💡 ここでは代表的なものを記載。必要に応じてリストを増やせます
    # 完全に600銘柄にするには、リストファイルを別途読み込むのが理想的です
    base_tickers = {
        "7203.T":"トヨタ", "9432.T":"NTT", "9984.T":"SBG", "6758.T":"ソニーG", "8306.T":"三菱UFJ",
        "8035.T":"東エレク", "6098.T":"リクルート", "4502.T":"武田", "2502.T":"アサヒ", "5401.T":"日本製鉄",
        "7267.T":"ホンダ", "9020.T":"JR東日本", "9433.T":"KDDI", "4063.T":"信越化", "6501.T":"日立",
        "6954.T":"ファナック", "4519.T":"中外薬", "6273.T":"SMC", "6367.T":"ダイキン", "3382.T":"7&i",
        "8001.T":"伊藤忠", "8058.T":"三菱商", "4503.T":"アステラス", "6723.T":"ルネサス", "6857.T":"アドバンテ"
        # ... ここに銘柄を追加していくことで600銘柄まで拡張可能
    }
    return base_tickers

# --- 📡 実行エンジン ---
def run_stealth_scan():
    send_discord("🔍 **【Jack株AI】ブロック回避・600銘柄バッチスキャンを開始...**")
    name_map = get_prime_600_list()
    tickers = list(name_map.keys())
    hits = {}
    
    # 💡 ブロックを避けるためのバッチサイズ (50銘柄ずつ)
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        print(f"📦 バッチ処理中 ({i+1}/{len(tickers)})...")
        
        try:
            # 💡 セッションをシミュレートしてお行儀よく取得
            data = yf.download(batch, period="1mo", interval="1d", progress=False, threads=False)
            close_data = data['Close'] if 'Close' in data else data
            
            for t in batch:
                try:
                    c = close_data[t].dropna() if isinstance(close_data, pd.DataFrame) else close_data.dropna()
                    if len(c) < 15: continue
                    rsi = calculate_rsi(c, 14).iloc[-1]
                    
                    # 逆張りチャンス判定
                    if not np.isnan(rsi) and (rsi <= 30 or rsi >= 70):
                        status = "📉 底圏" if rsi <= 30 else "📈 天井"
                        hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f})"}
                except: continue
        except Exception as e:
            print(f"Batch Error: {e}")
            time.sleep(30) # エラー時は30秒待機
        
        time.sleep(15) # バッチ間に15秒の休憩（Yahoo対策）

    # 強制保存
    result = {"date": get_jst_now().strftime('%Y-%m-%d %H:%M'), "hits": hits}
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    send_discord(f"✨ **【スキャン完了】** 候補銘柄：{len(hits)}件が見つかりました。")

if __name__ == "__main__":
    run_stealth_scan()
