import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time

# --- ⚙️ 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

TICKER_NAMES = {"2502.T": "アサヒ", "5401.T": "日本製鉄", "7267.T": "ホンダ", "9020.T": "JR東日本", "9432.T": "NTT", "9433.T": "KDDI"}
PRIME_TICKERS = list(TICKER_NAMES.keys())

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def run_prime_prescan():
    print(f"📡 スキャン開始時刻: {get_jst_now()}")
    hits = {}
    # 一括ダウンロード
    try:
        data = yf.download(PRIME_TICKERS, period="1mo", progress=False)
        if data.empty:
            print("❌ データが空です。yfinanceのバージョンを確認してください。")
            return
            
        close_data = data['Close']
        for t in PRIME_TICKERS:
            # RSI計算の代わりに、まずは「データがあるか」だけでテスト
            hits[t] = "監視中"
            print(f"✅ 検知: {t}")
    except Exception as e:
        print(f"❌ ダウンロードエラー: {e}")
    
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
    print(f"🏁 ファイル作成完了: {PRE_SCAN_FILE}")

def monitor_cycle():
    if not os.path.exists(WATCHLIST_FILE):
        print("ℹ️ 監視リスト(jack_watchlist.json)がないため、通知をスキップします。")
        return
    # 監視ロジック（中略）
    print("🔔 監視チェック実行中...")

if __name__ == "__main__":
    # 強制的に両方実行（テスト用）
    run_prime_prescan()
    monitor_cycle()
