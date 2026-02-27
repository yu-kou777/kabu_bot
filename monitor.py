import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time
import numpy as np

DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
JPX400_LIST = ['1605.T','1801.T','1802.T','1925.T','2502.T','2802.T','2914.T','4063.T','4502.T','4503.T','4519.T','4568.T','4901.T','5401.T','5713.T','6301.T','6367.T','6501.T','6758.T','6857.T','6920.T','6954.T','6981.T','7203.T','7267.T','7741.T','7974.T','8001.T','8031.T','8035.T','8058.T','8306.T','8316.T','8411.T','8766.T','8801.T','9020.T','9101.T','9104.T','9432.T','9433.T','9983.T','9984.T']

def calculate_rci(series, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

def daily_auto_scan():
    # 15時に実行されるJPX400全件スキャン
    all_d = yf.download(JPX400_LIST, period="100d", interval="1d", group_by='ticker', progress=False)
    hits = []
    for t in JPX400_LIST:
        try:
            df = all_d[t].dropna()
            r9 = calculate_rci(df['Close'], 9)
            # RSI計算
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
            
            # 条件：RCIピーク崩れ or 底打ち ＆ RSI過熱
            if r9.iloc[-1] > r9.iloc[-2] and r9.iloc[-2] < -80 and rsi < 35:
                hits.append(f"🚀 **{t}**: 買い転換サイン (RSI:{rsi:.1f})")
            elif r9.iloc[-1] < r9.iloc[-2] and r9.iloc[-2] > 80 and rsi > 65:
                hits.append(f"📉 **{t}**: 売り転換サイン (RSI:{rsi:.1f})")
        except: continue
    
    if hits:
        requests.post(DISCORD_URL, json={"content": "🕒 **15:00 大引け全銘柄速報**\n" + "\n".join(hits)})

if __name__ == "__main__":
    now = datetime.now(timezone(timedelta(hours=9))).time()
    # 15:00ちょうどに全銘柄を自動スキャン
    if dt_time(15, 0) <= now <= dt_time(15, 5):
        daily_auto_scan()
