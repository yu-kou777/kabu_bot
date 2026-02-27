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

# --- ☀️ 09:15 朝刊レポート ---
def morning_strategy_report():
    if not os.path.exists(WATCHLIST_FILE): return
    with open(WATCHLIST_FILE, 'r') as f: watchlist = json.load(f)
    tickers = [item['ticker'] for item in watchlist]
    
    send_discord("🌅 **【09:15 Jack株AI 朝刊レポート】**\n本日の監視銘柄の寄り付き前状況を確認します。")
    all_d = yf.download(tickers, period="5d", interval="1d", progress=False)
    
    report = []
    for t in tickers:
        try:
            df = all_d[t].dropna()
            r9 = calculate_rci(df['Close'], 9).iloc[-1]
            # RSI計算
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
            report.append(f"・**{t}**: RCI(9)={r9:.1f} / RSI={rsi:.1f}")
        except: continue
    
    if report: send_discord("\n".join(report) + "\n\n🚀 09:20より精密監視をスタートします！")

# --- 🕒 15:00 大引け速報（全銘柄スキャン） ---
def afternoon_daily_scan():
    send_discord("🕒 **15:00 大引け速報：JPX400全銘柄の日足複合分析を実行...**")
    all_d = yf.download(JPX400_LIST, period="100d", interval="1d", group_by='ticker', progress=False)
    hits = []
    for t in JPX400_LIST:
        try:
            df = all_d[t].dropna()
            r9 = calculate_rci(df['Close'], 9)
            if (r9.iloc[-1] > r9.iloc[-2] and r9.iloc[-2] < -80): hits.append(f"🚀 **{t}**: 買い転換サイン")
            elif (r9.iloc[-1] < r9.iloc[-2] and r9.iloc[-2] > 80): hits.append(f"📉 **{t}**: 売り転換サイン")
        except: continue
    if hits: send_discord("📢 **明日のための注目銘柄：**\n" + "\n".join(hits))
    else: send_discord("✅ 本日は目立った転換銘柄はありませんでした。")

# --- ☀️ 精密監視（法則判定） ---
def check_1m_logic(ticker):
    try:
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        if len(df) < 100: return
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df['MA60'] = df['Close'].rolling(60).mean()
        df['MA200'] = df['Close'].rolling(200).mean()
        # 20分タイムラグ確定
        is_strong = (df['MA60'].diff(20).iloc[-1] * df['MA200'].diff(20).iloc[-1] > 0)
        
        last = df.iloc[-1]; sigs = []
        if last['Low'] <= (df['Close'].rolling(20).mean() - (df['Close'].rolling(20).std() * 3)).iloc[-1]: sigs.append("🔥法則4:BB-3σ接触(買)")
        
        for s in sigs:
            label = "💎【超王道・20分確定】" if is_strong else "🔔"
            send_discord(f"{label} **{ticker}**\n{s}")
    except: pass

if __name__ == "__main__":
    jst_now = get_jst_now()
    now = jst_now.time()
    
    # 時間帯ごとの処理
    if dt_time(9, 15) <= now <= dt_time(9, 18): morning_strategy_report()
    elif dt_time(15, 0) <= now <= dt_time(15, 5): afternoon_daily_scan()
    elif (dt_time(9,20) <= now <= dt_time(11,50)) or (dt_time(12,50) <= now <= dt_time(15,20)):
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r') as f:
                for item in json.load(f): check_1m_logic(item['ticker'])
