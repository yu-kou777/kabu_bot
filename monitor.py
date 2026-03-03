import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import numpy as np
from datetime import datetime, timedelta, timezone, time as dt_time

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"
JPX_LIST_URL = "https://www.jpx.co.jp/markets/statistics-banner/quote/tvdivq0000001vg2-att/data_j.xls"

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# --- 📋 プライム銘柄リストの自動取得 ---
def get_prime_tickers():
    print("🌐 JPXから最新の銘柄リストを取得中...")
    try:
        res = requests.get(JPX_LIST_URL)
        df = pd.read_excel(res.content)
        # 「市場・商品区分」が「プライム（内国株式）」のものを抽出
        prime_df = df[df['市場・商品区分'].str.contains('プライム', na=False)]
        tickers = [f"{code}.T" for code in prime_df['コード']]
        print(f"✅ プライム市場 {len(tickers)} 銘柄を特定しました。")
        return tickers
    except Exception as e:
        print(f"❌ リスト取得失敗: {e}")
        return ["9432.T", "7203.T", "9984.T"] # 失敗時のバックアップ

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

# --- 📡 1. 朝の日足全件スキャン ---
def run_full_daily_scan():
    tickers = get_prime_tickers()
    hits = {}
    chunk_size = 50 # 50銘柄ずつ小分けにダウンロード（エラー回避）
    
    print(f"📡 全件スキャン開始: {get_jst_now()}")
    for i in range(0, len(tickers), chunk_size):
        batch = tickers[i : i + chunk_size]
        try:
            # 負荷を分散させながら取得
            data = yf.download(batch, period="1y", progress=False)['Close']
            for t in batch:
                if t not in data or data[t].isnull().all(): continue
                c = data[t].dropna()
                if len(c) < 30: continue
                
                rsi = calculate_rsi(c, 14).iloc[-1]
                rci = calculate_rci(c, 9).iloc[-1]
                
                # ✅ ジャックさんの「お宝条件」
                if (rsi <= 20 and rci <= -70) or (rsi >= 90 and rci >= 95):
                    hits[t] = f"極値(RSI:{rsi:.0f}/RCI:{rci:.0f})"
        except:
            continue
        time.sleep(2) # 2秒待機してYahooの制限を回避
        if i % 200 == 0: print(f"📊 進捗: {i}/{len(tickers)} 銘柄完了...")

    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
    
    # Discordに完了報告
    requests.post(DISCORD_URL, json={"content": f"✅ **【Jack株AI】全件スキャン完了**\n本日のお宝候補は **{len(hits)}件** です。"})

# (monitor_cycle関数は以前と同じものを使用)
