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
        # データ取得 (最新のMultiIndex問題に対応)
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if len(df) < 60: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標計算
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['MA60'] = ta.sma(df['Close'], length=60)
        df['MA200'] = ta.sma(df['Close'], length=200)
        df['MA60_s'] = df['MA60'].diff(); df['MA200_s'] = df['MA200'].diff()
        bb2 = ta.bbands(df['Close'], length=20, std=2)
        bb3 = ta.bbands(df['Close'], length=20, std=3)
        df['BB_u2'] = bb2['BBU_20_2.0']; df['BB_l2'] = bb2['BBL_20_2.0']; df['BB_l3'] = bb3['BBL_20_3.0']

        last = df.iloc[-1]; sigs = []
        rsi_txt = f"(RSI:{last['RSI']:.1f})"
        
        # トレンド判定 (法則8: 傾きの一致)
        is_same_down = (last['MA60_s'] < 0) and (last['MA200_s'] < 0)
        is_same_up = (last['MA60_s'] > 0) and (last['MA200_s'] > 0)

        # RSI 10/80 検知
        if last['RSI'] <= 10 or last['RSI'] >= 80: sigs.append(f"🚨【RSI極限】{rsi_txt}")
        
        # --- 7つの法則判定 ---
        if last['Close'] > last['MA60']: # 60MAより上
            if (df['High'].tail(10) >= df['BB_u2'].tail(10)).sum() >= 3: sigs.append(f"法則1:BB+2σx3(売)")
            if last['Low'] <= last['MA60']: sigs.append(f"法則2:60MA反発(買)")
            if last['MA200'] > last['MA60'] and last['High'] >= last['MA200']: sigs.append(f"法則3:200MA抵抗(売)")
        else: # 60MAより下
            if last['Low'] <= last['BB_l3']: sigs.append(f"法則4:BB-3σ接触(買)")
            if last['Low'] <= last['MA200']: sigs.append(f"法則5:200MA反発(買)")
            if last['High'] >= last['MA60']: sigs.append(f"法則6:60MA反発(売)")
            if last['Close'] > last['MA60']: sigs.append(f"法則6:60MA突破(買)")
            if (df['Low'].tail(10) <= df['BB_l2'].tail(10)).sum() >= 3: sigs.append(f"法則7:BB-2σx3(買)")

        # 法則8適用時のラベル
        for s in sigs:
            label = "💎【超王道】" if (is_same_down or is_same_up) else "🔔"
            send_discord(f"{label} **{ticker}**\n{s} {rsi_txt}")
    except: pass

if __name__ == "__main__":
    now = get_jst_now().time()
    if (dt_time(9,20) <= now <= dt_time(11,50)) or (dt_time(12,50) <= now <= dt_time(15,20)):
        watchlist = load_watchlist()
        for item in watchlist: check_logic(item['ticker'])
