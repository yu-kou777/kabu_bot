import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time
import numpy as np

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"

# JPX400の主要銘柄リスト（400銘柄まで拡張可能）
JPX400_LIST = ['1605.T','1801.T','1802.T','1925.T','2502.T','2802.T','2914.T','4063.T','4502.T','4503.T','4519.T','4568.T','4901.T','5401.T','5713.T','6301.T','6367.T','6501.T','6758.T','6857.T','6920.T','6954.T','6981.T','7203.T','7267.T','7741.T','7974.T','8001.T','8031.T','8035.T','8058.T','8306.T','8316.T','8411.T','8766.T','8801.T','9020.T','9101.T','9104.T','9432.T','9433.T','9983.T','9984.T']

def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rci(series, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- 15時専用：日足複合分析（RCIピーク崩れ ＆ RSI） ---
def daily_composite_scan():
    send_discord("🕒 **15:00 定期スキャン開始：JPX400銘柄の日足分析を実行中...**")
    all_data = yf.download(JPX400_LIST, period="100d", interval="1d", group_by='ticker', progress=False)
    hits = []
    
    for t in JPX400_LIST:
        try:
            df = all_data[t].dropna()
            if len(df) < 20: continue
            
            # RCI(9)
            rci9 = calculate_rci(df['Close'], 9)
            last_r9, prev_r9 = rci9.iloc[-1], rci9.iloc[-2]
            
            # RSI(14)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rsi = 100 - (100 / (1 + (gain / loss)))
            last_rsi = rsi.iloc[-1]
            
            # 判定ロジック
            if last_r9 < prev_r9 and prev_r9 > 80 and last_rsi > 70:
                hits.append(f"📉 **{t}**: 【明日売り】RCIピーク崩れ/RSI過熱({last_rsi:.1f})")
            elif last_r9 > prev_r9 and prev_r9 < -80 and last_rsi < 30:
                hits.append(f"🚀 **{t}**: 【明日買い】RCI底打ち/RSI割安({last_rsi:.1f})")
        except: continue
        
    if hits:
        send_discord("📢 **【15:00 大引け速報】転換点の銘柄を検知しました**\n" + "\n".join(hits))
    else:
        send_discord("✅ 15:00 スキャン完了：現在、日足ベースでの強い転換サインはありません。")

if __name__ == "__main__":
    now = get_jst_now().time()
    
    # 15:00〜15:05の間に1回実行
    if dt_time(15, 0) <= now <= dt_time(15, 5):
        daily_composite_scan()
    
    # 通常の精密監視（9:20-15:20の間、登録銘柄のみ）
    if (dt_time(9,20) <= now <= dt_time(11,50)) or (dt_time(12,50) <= now <= dt_time(15,20)):
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                for item in json.load(f):
                    # ここに既存の1分足判定ロジック（法則4, 6など）を呼び出す
                    pass
