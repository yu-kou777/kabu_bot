import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"

def send_discord(message):
    try:
        requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except:
        pass

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def check_logic(ticker):
    try:
        # 1分足データを取得
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if df.empty: return
        
        # 2次元配列（MultiIndex）対策
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # RSI(14) の計算
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        last = df.iloc[-1]
        rsi_val = last['RSI']
        
        # --- RSI極限検知 (10以下 または 80以上) ---
        if rsi_val <= 10 or rsi_val >= 80:
            status = "📉 超売られすぎ" if rsi_val <= 10 else "📈 超買われすぎ"
            message = f"🚨 **【RSI警告】{ticker}**\n{status}\n現在のRSI: **{rsi_val:.2f}**"
            send_discord(message)
            print(f"Match found: {ticker} RSI {rsi_val}")
            
    except Exception as e:
        print(f"Error checking {ticker}: {e}")

if __name__ == "__main__":
    jst_now = get_jst_now()
    now_time = jst_now.time()
    
    # 監視時間内かチェック (9:20-11:50, 12:50-15:20)
    is_trading = (dt_time(9, 20) <= now_time <= dt_time(11, 50)) or \
                 (dt_time(12, 50) <= now_time <= dt_time(15, 20))
    
    if is_trading:
        watchlist = load_watchlist()
        if not watchlist:
            print("Watchlist is empty.")
        for item in watchlist:
            check_logic(item['ticker'])
    else:
        print(f"Outside trading hours: {now_time}")

