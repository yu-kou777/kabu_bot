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

# --- RCI計算関数 ---
def calculate_rci(series, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- ① 1分足監視（20分のタイムラグ・傾き計算） ---
def check_1m_logic(ticker):
    try:
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        if len(df) < 200: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 指標計算
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA200'] = df['Close'].rolling(window=200).mean()
        
        # 【新機能】20分間の移動平均の傾きを計算（タイムラグの考慮）
        # 現在と20分前の差を見て、トレンドが継続しているか判定
        df['MA60_slope_20'] = df['MA60'] - df['MA60'].shift(20)
        df['MA200_slope_20'] = df['MA200'] - df['MA200'].shift(20)
        
        std = df['Close'].rolling(window=20).std()
        ma20 = df['Close'].rolling(window=20).mean()
        df['BB_u2'] = ma20 + (std * 2)
        df['BB_l2'] = ma20 - (std * 2)
        df['BB_l3'] = ma20 - (std * 3)

        last = df.iloc[-1]; sigs = []
        # 法則8: 20分間の傾きが一致しているか
        is_strong_trend = (last['MA60_slope_20'] * last['MA200_slope_20'] > 0)

        # 法則判定（画像に基づき1〜7を網羅）
        if last['Close'] > last['MA60']:
            if (df['High'].tail(10) >= df['BB_u2'].tail(10)).sum() >= 3: sigs.append("法則1:BB+2σx3(売)")
            if last['Low'] <= last['MA60']: sigs.append("法則2:60MA反発(買)")
        else:
            if last['Low'] <= last['BB_l3']: sigs.append("法則4:BB-3σ接触(買)")
            if last['High'] >= last['MA60']: sigs.append("法則6:60MA反発(売)")
            if (df['Low'].tail(10) <= df['BB_l2'].tail(10)).sum() >= 3: sigs.append("法則7:BB-2σx3(買)")

        for s in sigs:
            prefix = "💎【超王道・20分確定】" if is_strong_trend else "🔔"
            send_discord(f"{prefix} **{ticker}**\n{s}")
    except: pass

# --- ② 15時ジャスト：日足RCI・RSI速報（明日の仕込み用） ---
def check_daily_flash(ticker):
    try:
        df = yf.download(ticker, period="100d", interval="1d", progress=False)
        if len(df) < 60: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        # RCI(9)のピーク崩れ検知
        rci9 = calculate_rci(df['Close'], 9)
        last_r9, prev_r9 = rci9.iloc[-1], rci9.iloc[-2]
        
        # RSI(14)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = 100 - (100 / (1 + (gain / loss)))
        last_rsi = rsi.iloc[-1]

        report = ""
        # 売り予測：RCIが天井(80)から下落 ＆ RSIが買われすぎ(70以上)
        if last_r9 < prev_r9 and prev_r9 > 80 and last_rsi > 70:
            report = "📉 【明日売り予測】RCIピーク崩れ ＆ RSI過熱"
        # 買い予測：RCIが底(-80)から上昇 ＆ RSIが売られすぎ(30以下)
        elif last_r9 > prev_r9 and prev_r9 < -80 and last_rsi < 30:
            report = "🚀 【明日買い予測】RCI底打ち ＆ RSI割安"

        if report:
            send_discord(f"🕒 **15:00 大引け速報：{ticker}**\n{report}\nRCI9: {last_r9:.1f} / RSI: {last_rsi:.1f}")
    except: pass

if __name__ == "__main__":
    jst_now = get_jst_now()
    now_time = jst_now.time()
    
    # 監視銘柄リストを読み込み
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f:
            watchlist = json.load(f)
            
            # A. 15時00分〜15時05分の間だけ「日足速報」を実行
            if dt_time(15, 0) <= now_time <= dt_time(15, 5):
                for item in watchlist: check_daily_flash(item['ticker'])
            
            # B. 通常の取引時間（1分足監視）
            if (dt_time(9,20) <= now_time <= dt_time(11,50)) or (dt_time(12,50) <= now_time <= dt_time(15,20)):
                for item in watchlist: check_1m_logic(item['ticker'])
