import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
import numpy as np
from datetime import datetime, timedelta, timezone

# --- ⚙️ 基本設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

TICKER_NAMES = {
    "2502.T": "アサヒ", "5401.T": "日本製鉄", "7267.T": "ホンダ",
    "9020.T": "JR東日本", "9432.T": "NTT", "9433.T": "KDDI"
}
PRIME_TICKERS = list(TICKER_NAMES.keys()) + ["1605.T", "7203.T", "8035.T", "9984.T"]

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# --- 📡 1. 日足スキャン ---
def run_daily_scan():
    print(f"🚀 【テスト】日足スキャン開始: {get_jst_now()}")
    hits = {}
    try:
        data = yf.download(PRIME_TICKERS, period="1y", progress=False)
        # Close列だけを抽出
        close_df = data['Close']
        for t in PRIME_TICKERS:
            if t in close_df:
                hits[t] = "テスト検知"
        with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
            json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
        print(f"✅ スキャン結果を保存しました")
    except Exception as e:
        print(f"❌ スキャンエラー: {e}")

# --- 🔔 2. 監視通知（データ抽出を確実に修正） ---
def monitor_cycle():
    print(f"🔔 【テスト】監視サイクル開始: {get_jst_now()}")
    report_blocks = []
    
    for t in TICKER_NAMES.keys():
        try:
            # 1分足データを取得
            df = yf.download(t, period="1d", interval="1m", progress=False)
            if df.empty:
                df = yf.download(t, period="1d", progress=False)
            
            # ✅ 修正ポイント：確実にスカラ値（単一の数値）として取得
            if isinstance(df['Close'], pd.DataFrame):
                val = df['Close'].iloc[-1, 0] # 複数列ある場合
            else:
                val = df['Close'].iloc[-1]   # 1列の場合
            
            now_p = float(val) # 数値に変換
            report_blocks.append(f"🔹**{TICKER_NAMES[t]}** `{now_p:,.1f}円` | 正常に通信中 ✅")
            print(f"✅ {t}: {now_p}")
        except Exception as e:
            print(f"⚠️ {t} でエラー: {e}")
            continue

    if report_blocks:
        msg = f"🧪 **【Jack株AI：夜間動作テスト】**\n" + "\n".join(report_blocks)
        res = requests.post(DISCORD_URL, json={"content": msg})
        print(f"📤 Discord送信結果: {res.status_code}")
    else:
        print("ℹ️ 通知するデータがありませんでした。")

if __name__ == "__main__":
    run_daily_scan()
    monitor_cycle()
