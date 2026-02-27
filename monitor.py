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

def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# RCI計算
def calculate_rci(series, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- ① 通常監視（20分タイムラグ計算） ---
def check_1m_logic(ticker):
    try:
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        if len(df) < 100: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標計算
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA200'] = df['Close'].rolling(window=200).mean()
        
        # 【新機能】20分間のMAの傾き（タイムラグ）を計算
        df['MA60_slope_20'] = df['MA60'] - df['MA60'].shift(20)
        df['MA200_slope_20'] = df['MA200'] - df['MA200'].shift(20)
        
        ma20 = df['Close'].rolling(window=20).mean()
        std20 = df['Close'].rolling(window=20).std()
        df['BB_u2'] = ma20 + (std20 * 2); df['BB_l3'] = ma20 - (std20 * 3)

        last = df.iloc[-1]; sigs = []
        is_strong = (last['MA60_slope_20'] * last['MA200_slope_20'] > 0) # 20分間同じ向き

        # 法則判定
        if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_u2'].tail(10)).sum() >= 3:
            sigs.append("法則1:BB+2σx3(売)")
        if last['Low'] <= last['BB_l3']: sigs.append("🔥法則4:BB-3σ接触(買)")
        if last['Close'] < last['MA60'] and last['High'] >= last['MA60']: sigs.append("💎法則6:60MA反発(売)")

        for s in sigs:
            label = "💎【超王道・20分確定】" if is_strong else "🔔"
            send_discord(f"{label} **{ticker}**\n{s}")
    except: pass

# --- ② 15時大引け前速報（明日への予測） ---
def check_daily_flash(ticker):
    try:
        df = yf.download(ticker, period="100d", interval="1d", progress=False)
        if len(df) < 60: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # RCI(9)の反転検知
        rci9 = calculate_rci(df['Close'], 9)
        last_r9, prev_r9 = rci9.iloc[-1], rci9.iloc[-2]
        
        # RSI(14)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = 100 - (100 / (1 + (gain / loss)))
        last_rsi = rsi.iloc[-1]

        report = ""
        if last_r9 < prev_r9 and prev_r9 > 80 and last_rsi > 70: report = "📉 【明日売り予測】RCIピーク崩れ ＆ RSI過熱"
        elif last_r9 > prev_r9 and prev_r9 < -80 and last_rsi < 30: report = "🚀 【明日買い予測】RCI底打ち ＆ RSI売られすぎ"

        if report:
            send_discord(f"🕒 **15:00 大引け速報：{ticker}**\n{report}\nRCI9: {last_r9:.1f} / RSI: {last_rsi:.1f}")
    except: pass

if __name__ == "__main__":
    jst_now = get_jst_now()
    now_time = jst_now.time()
    
    # 【テスト用】起動時に一度挨拶（接続確認）
    send_discord(f"✅ 【システム】監視ボット稼働中（{jst_now.strftime('%H:%M')}）")

    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f:
            watchlist = json.load(f)
            # A. 15時ジャストの速報
            if dt_time(15, 0) <= now_time <= dt_time(15, 5):
                for item in watchlist: check_daily_flash(item['ticker'])
            # B. 通常監視
            if (dt_time(9,20) <= now_time <= dt_time(11,50)) or (dt_time(12,50) <= now_time <= dt_time(15,20)):
                for item in watchlist: check_1m_logic(item['ticker'])
