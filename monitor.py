import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time

DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"

def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# --- ライブラリを使わない指標計算 ---
def check_logic(ticker):
    try:
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        if len(df) < 60: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 移動平均 (MA)
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA200'] = df['Close'].rolling(window=200).mean()
        
        # ボリンジャーバンド (BB)
        std = df['Close'].rolling(window=20).std()
        ma20 = df['Close'].rolling(window=20).mean()
        df['BB_u2'] = ma20 + (std * 2)
        df['BB_l2'] = ma20 - (std * 2)
        df['BB_l3'] = ma20 - (std * 3)
        
        # RSI (14) の手動計算
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        last = df.iloc[-1]; sigs = []
        rsi_txt = f"(RSI:{last['RSI']:.1f})"

        # RSI極限
        if last['RSI'] <= 10 or last['RSI'] >= 80: sigs.append(f"🚨【RSI警告】{rsi_txt}")
        
        # 7つの法則判定
        if last['Close'] > last['MA60']:
            if (df['High'].tail(10) >= df['BB_u2'].tail(10)).sum() >= 3: sigs.append(f"法則1:BB+2σx3(売)")
        else:
            if last['Low'] <= last['BB_l3']: sigs.append(f"法則4:BB-3σ接触(買)")
            if last['High'] >= last['MA60']: sigs.append(f"法則6:60MA反発(売)")

        for s in sigs:
            send_discord(f"🔔 **{ticker}**\n{s} {rsi_txt}")
    except: pass

if __name__ == "__main__":
    now = get_jst_now().time()
    if (dt_time(9,20) <= now <= dt_time(11,50)) or (dt_time(12,50) <= now <= dt_time(15,20)):
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                for item in json.load(f): check_logic(item['ticker'])
