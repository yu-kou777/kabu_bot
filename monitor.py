import yfinance as yf
import pandas as pd
import pandas_ta as ta
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

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f: return json.load(f)
        except: return []
    return []

def check_logic(ticker):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if df.empty: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # RSI(14)を計算
        df['RSI'] = ta.rsi(df['Close'], length=14)
        last = df.iloc[-1]
        rsi_val = last['RSI']
        
        # RSI極限検知 (10以下 または 80以上)
        if rsi_val <= 10 or rsi_val >= 80:
            status = "📉 売られすぎ" if rsi_val <= 10 else "📈 買われすぎ"
            send_discord(f"🚨 **【RSI警告】{ticker}**\n{status}\n現在のRSI: **{rsi_val:.1f}**")
    except: pass

if __name__ == "__main__":
    now = get_jst_now().time()
    # 監視時間内 (9:20-11:50, 12:50-15:20) かチェック
    if (dt_time(9, 20) <= now <= dt_time(11, 50)) or (dt_time(12, 50) <= now <= dt_time(15, 20)):
        watchlist = load_watchlist()
        for item in watchlist:
            check_logic(item['ticker'])
