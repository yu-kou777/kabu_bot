import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import io
import random
import numpy as np
from datetime import datetime, timedelta, timezone

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
PRE_SCAN_FILE = "pre_scan_results.json"
WATCHLIST_FILE = "jack_watchlist.json"
JPX_LIST_URL = "https://www.jpx.co.jp/markets/statistics-banner/quote/tvdivq0000001vg2-att/data_j.xls"

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_discord(msg):
    try: requests.post(DISCORD_URL, json={"content": msg}, timeout=10)
    except: print(f"Discord送信失敗")

def calculate_rsi(series, period=14):
    if len(series) < period: return pd.Series([np.nan]*len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- 📋 ターゲット600銘柄の選定 ---
def get_600_tickers():
    try:
        # User-Agentを偽装してJPXから取得
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(JPX_LIST_URL, headers=headers, timeout=30)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)].head(600)
        return {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except:
        # JPXに拒否された場合の予備リスト
        return {"7203.T":"トヨタ", "9432.T":"NTT", "9984.T":"SBG", "6758.T":"ソニーG", "8306.T":"三菱UFJ"}

# --- 📡 実行エンジン ---
def run_slow_scan():
    send_discord("🔍 **【Jack株AI】600銘柄の超低速スキャンを開始します...（推定完了：1時間後）**")
    name_map = get_600_tickers()
    tickers = list(name_map.keys())
    hits = {}
    
    print(f"📡 総ターゲット: {len(tickers)} 銘柄")
    
    for i, t in enumerate(tickers):
        try:
            # 💡 1銘柄ずつ個別に取得（一括ダウンロードを避ける）
            ticker_obj = yf.Ticker(t)
            data = ticker_obj.history(period="1mo")
            
            if not data.empty:
                c = data['Close']
                rsi = calculate_rsi(c, 14).iloc[-1]
                
                # RSI 30以下 または 70以上
                if not np.isnan(rsi) and (rsi <= 30 or rsi >= 70):
                    status = "📉 底圏" if rsi <= 30 else "📈 天井"
                    hits[t] = {"name": name_map[t], "reason": f"{status}(RSI:{rsi:.0f})"}
                    print(f"✨ ヒット: {name_map[t]} ({t}) RSI:{rsi:.1f}")
            
        except Exception as e:
            print(f"❌ {t} エラー: {e}")
            time.sleep(10) # エラー時は長めに休む
        
        # ✅ 重要：1銘柄ごとに3〜7秒のランダム休憩を入れる（人間らしさの演出）
        wait_time = random.uniform(3, 7)
        time.sleep(wait_time)
        
        if (i + 1) % 50 == 0:
            print(f"📊 進捗: {i+1}/{len(tickers)} 完了...")
            # 50銘柄ごとにファイルを中間保存
            temp_data = {"date": get_jst_now().strftime('%Y-%m-%d %H:%M'), "hits": hits}
            with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
                json.dump(temp_data, f, ensure_ascii=False, indent=2)

    # 最終保存
    result_data = {"date": get_jst_now().strftime('%Y-%m-%d %H:%M'), "hits": hits}
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    send_discord(f"✨ **【スキャン完了】** 全600銘柄の精査が終わりました。候補：**{len(hits)}件**")

if __name__ == "__main__":
    run_slow_scan()
