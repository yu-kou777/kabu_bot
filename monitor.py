import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time
import numpy as np

DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
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

# --- ① 1分足：黄金法則判定ロジック ---
def check_1m_logic(item):
    ticker = item['ticker']
    reason = item.get('reason', '監視銘柄')
    try:
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        if len(df) < 200: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標計算
        close = df['Close']
        ma60 = close.rolling(60).mean()
        ma200 = close.rolling(200).mean()
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_u2 = ma20 + (std20 * 2)
        bb_l2 = ma20 - (std20 * 2)
        bb_l3 = ma20 - (std20 * 3)
        
        # RSI(14)計算
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss)))
        
        # トレンド判定（20分タイムラグ確定）
        slope60 = ma60.diff(20).iloc[-1]
        slope200 = ma200.diff(20).iloc[-1]
        is_strong = (slope60 * slope200 > 0)
        
        last = df.iloc[-1]; sigs = []
        l_close = last['Close']
        l_ma60 = ma60.iloc[-1]
        l_ma200 = ma200.iloc[-1]
        
        # --- 画像の条件を判定 ---
        # 1. 60MAより上、BB+2σに3回接触 -> 売り
        if l_close > l_ma60:
            if (df['High'].tail(10) >= bb_u2.tail(10)).sum() >= 3: sigs.append("法則1:BB+2σx3(売)")
            # 2. 60MA反発(買) / 割り込み(売)
            if last['Low'] <= l_ma60: sigs.append("法則2:60MA反発(買)/下抜(売)")
            # 3. 200MAが60MAより上で、200MAに接触 -> 売り
            if l_ma200 > l_ma60 and last['High'] >= l_ma200: sigs.append("法則3:200MA接触(売)")
        
        # 4. 60MAより下、BB-3σに接触 -> 買い
        else:
            if last['Low'] <= bb_l3.iloc[-1]: sigs.append("法則4:BB-3σ接触(買)")
            # 5. 200MA反発(買) / 割り込み(売)
            if last['Low'] <= l_ma200: sigs.append("法則5:200MA反発(買)/下抜(売)")
            # 6. 60MA反発(売) / 越え(買)
            if last['High'] >= l_ma60: sigs.append("法則6:60MA反発(売)/上抜(買)")
            # 7. BB-2σに3回接触 -> 買い
            if (df['Low'].tail(10) <= bb_l2.tail(10)).sum() >= 3: sigs.append("法則7:BB-2σx3(買)")
        
        # RSIの極限値アラート
        l_rsi = rsi.iloc[-1]
        if l_rsi <= 15: sigs.append(f"🚨RSI超低迷({l_rsi:.1f})")
        if l_rsi >= 85: sigs.append(f"🚨RSI超高騰({l_rsi:.1f})")

        for s in sigs:
            label = "💎【超王道・20分確定】" if is_strong else "🔔"
            send_discord(f"{label} **【{reason}】{ticker}**\n{s}")
    except: pass

# --- ② 15時：日足複合分析（RCIとRSIを活用） ---
def afternoon_daily_scan():
    send_discord("🕒 **15:00 大引け速報：全銘柄の日足RCI・RSI分析を実行中...**")
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
            rsi = 100 - (100 / (1 + (gain / loss)))
            
            l_r9, p_r9 = r9.iloc[-1], r9.iloc[-2]
            l_rsi = rsi.iloc[-1]
            
            # 日足はRCIとRSIのピークを複合判定
            if l_r9 > p_r9 and p_r9 < -80 and l_rsi < 35: hits.append(f"🚀 **{t}**: 買い転換サイン")
            elif l_r9 < p_r9 and p_r9 > 80 and l_rsi > 65: hits.append(f"📉 **{t}**: 売り転換サイン")
        except: continue
    if hits: send_discord("📢 **明日のための注目銘柄：**\n" + "\n".join(hits))
    else: send_discord("✅ 本日は強い転換サインはありませんでした。")

if __name__ == "__main__":
    jst_now = get_jst_now()
    now = jst_now.time()
    if dt_time(15, 0) <= now <= dt_time(15, 5): afternoon_daily_scan()
    elif (dt_time(9,20) <= now <= dt_time(11,50)) or (dt_time(12,50) <= now <= dt_time(15,20)):
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                watchlist = json.load(f)
                for item in watchlist: check_1m_logic(item)
