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
        # 1年分のデータを取得
        data = yf.download(PRIME_TICKERS, period="1y", progress=False)
        close_df = data['Close']
        
        for t in PRIME_TICKERS:
            if t in close_df:
                hits[t] = "テスト検知"
        
        with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
            json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
        print(f"✅ スキャン結果を保存しました: {len(hits)}件")
    except Exception as e:
        print(f"❌ スキャンエラー: {e}")

# --- 🔔 2. 監視通知（エラー修正版） ---
def monitor_cycle():
    print(f"🔔 【テスト】監視サイクル開始: {get_jst_now()}")
    report_blocks = []
    
    # テストとして、監視リストがなくても主要6銘柄をチェック
    for t in TICKER_NAMES.keys():
        try:
            # 1分足データを取得
            df = yf.download(t, period="2d", interval="1m", progress=False)
            if df.empty:
                print(f"⚠️ {t} の1分足データが空です（市場閉場中）")
                # テスト用に最新価格だけ取得
                df = yf.download(t, period="1d", progress=False)
            
            # データの取り出し方を修正（1つの銘柄でもエラーにならないように）
            now_p = df['Close'].iloc[-1]
            report_blocks.append(f"🔹**{TICKER_NAMES[t]}** `{now_p:,.1f}円` | 正常に通信中 ✅")
        except Exception as e:
            print(f"⚠️ {t} でエラー: {e}")
            continue

    if report_blocks:
        msg = f"🧪 **【Jack株AI：夜間動作テスト】**\n" + "\n".join(report_blocks)
        payload = {"content": msg}
        res = requests.post(DISCORD_URL, json=payload)
        print(f"📤 Discord送信結果: {res.status_code} (204なら成功)")
    else:
        print("ℹ️ 通知するデータがありませんでした。")

if __name__ == "__main__":
    run_daily_scan()
    monitor_cycle()
