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

def check_logic_1m(item):
    ticker = item['ticker']
    reason = item.get('reason', '監視銘柄')
    try:
        # 1分足データを取得
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        if len(df) < 200: return
        
        # データ構造の整理
        close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        high = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']
        low = df['Low'].iloc[:, 0] if isinstance(df['Low'], pd.DataFrame) else df['Low']
        close = close.dropna(); high = high.dropna(); low = low.dropna()

        # 指標計算
        ma60 = close.rolling(60).mean()
        ma200 = close.rolling(200).mean()
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_u2 = ma20 + (std20 * 2)
        bb_l2 = ma20 - (std20 * 2)
        bb_l3 = ma20 - (std20 * 3)
        
        # ✅ 条件8：トレンド方向判定（20分タイムラグ確定）
        is_strong = (ma60.diff(20).iloc[-1] * ma200.diff(20).iloc[-1] > 0)
        
        sigs = []
        l_c = close.iloc[-1]; l_h = high.iloc[-1]; l_l = low.iloc[-1]
        l_ma60 = ma60.iloc[-1]; l_ma200 = ma200.iloc[-1]

        # --- 画像の条件判定開始 ---

        if l_c > l_ma60:
            # 1. 60日線より上、BB+2σに3回接触 -> 売り
            if (high.tail(15) >= bb_u2.tail(15)).sum() >= 3: sigs.append("法則1: BB+2σx3(売)")
            
            # 2. 60日線に触れたら買い / 割り込んだら売り
            if l_l <= l_ma60: sigs.append("法則2: 60MA反発(買) / 下抜(売)")
            
            # 3. 200日線が60日線より上で、200日線に接触 -> 売り
            if l_ma200 > l_ma60 and l_h >= l_ma200: sigs.append("法則3: 200MA接触(売)")
        
        else: # 60日線より下
            # 4. BB-3σに触れたら買い
            if l_l <= bb_l3.iloc[-1]: sigs.append("法則4: BB-3σ接触(買)")
            
            # 5. 200日線に触れたら買い / 割り込んだら売り
            if l_l <= l_ma200: sigs.append("法則5: 200MA反発(買) / 下抜(売)")
            
            # 6. 60日線に触れたら売り / 超えたら買い
            if l_h >= l_ma60: sigs.append("法則6: 60MA反発(売) / 上抜(買)")
            
            # 7. 60日線より下、BB-2σに3回接触 -> 買い
            if (low.tail(15) <= bb_l2.tail(15)).sum() >= 3: sigs.append("法則7: BB-2σx3(買)")

        # 通知の送信
        for s in sigs:
            label = "💎【超王道・トレンド確定】" if is_strong else "🔔"
            send_discord(f"{label} **【{reason}】{ticker}**\n{s}")

    except: pass

if __name__ == "__main__":
    now = get_jst_now().time()
    # 取引時間中のみ監視 (9:20-11:30, 12:40-15:10)
    if (dt_time(9,20) <= now <= dt_time(11,30)) or (dt_time(12,40) <= now <= dt_time(15,10)):
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                watchlist = json.load(f)
                for item in watchlist: check_logic_1m(item)
