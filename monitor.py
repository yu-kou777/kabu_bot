import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime, timedelta, timezone, time as dt_time

# --- ⚙️ 設定エリア ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

# 監視スケジュール（日本時間）
MONITOR_START = "09:20"
MONITOR_END = "15:10"

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def is_market_open():
    now = get_jst_now()
    if now.weekday() >= 5: return False
    curr = now.time()
    return (dt_time(9, 20) <= curr <= dt_time(11, 30)) or (dt_time(12, 40) <= curr <= dt_time(15, 10))

def get_prediction_logic(close, volume, ma60, ma200):
    """出来高急増とトレンド傾きによる推移予測"""
    s60 = ma60.diff(20).iloc[-1]
    s200 = ma200.diff(20).iloc[-1]
    avg_v = volume.tail(30).mean()
    vol_ratio = (volume.iloc[-1] / avg_v) if avg_v > 0 else 0
    is_spike = vol_ratio >= 2.5
    
    spike_msg = f"🔥 **【出来高急増】{vol_ratio:.1f}倍**" if is_spike else ""
    if s60 > 0 and s200 > 0: pred = "📈 **上昇強気**"
    elif s60 < 0 and s200 < 0: pred = "📉 **下落継続**"
    else: pred = "🔄 **反転の兆し**"
    
    return spike_msg, pred, is_spike

def monitor_cycle():
    """全銘柄をスキャンし、チャンスがある銘柄だけをまとめて通知"""
    if not os.path.exists(WATCHLIST_FILE): return
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if not watchlist: return

    report_blocks = [] # 条件に合った銘柄の情報を入れるリスト

    for item in watchlist:
        ticker = item['ticker']
        name_jp = item.get('name', ticker) # 和名の取得
        
        try:
            df = yf.download(ticker, period="2d", interval="1m", progress=False)
            if df.empty: continue
            
            c = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
            v = df['Volume'].iloc[:, 0] if isinstance(df['Volume'], pd.DataFrame) else df['Volume']
            ma60, ma200 = c.rolling(60).mean(), c.rolling(200).mean()
            ma20 = c.rolling(20).mean(); std20 = c.rolling(20).std()
            bb_u2, bb_l2 = ma20 + (std20 * 2), ma20 - (std20 * 2)

            now_p = c.iloc[-1]
            sigs = []
            
            # 法則判定
            if now_p > ma60.iloc[-1] and (df['High'].iloc[:,0].tail(15) >= bb_u2.tail(15)).sum() >= 3:
                sigs.append("⚠️ 法則1 (天井圏売り検討)")
            if now_p < ma60.iloc[-1] and (df['Low'].iloc[:,0].tail(15) <= bb_l2.tail(15)).sum() >= 3:
                sigs.append("⚠️ 法則7 (底打ち買い検討)")
            
            is_strong = (ma60.diff(20).iloc[-1] * ma200.diff(20).iloc[-1] > 0)
            spike_msg, pred, is_spike = get_prediction_logic(c, v, ma60, ma200)

            # ✅ 通知条件：法則合致、または法則8確定、または出来高急増
            if sigs or is_strong or is_spike:
                block = f"🔹 **{name_jp} ({ticker})** `{now_p:,.1f}円`\n"
                if sigs: block += "\n".join(sigs) + "\n"
                if is_strong: block += "💎 **法則8確定 (強トレンド)**\n"
                block += f"{spike_msg} {pred}\n"
                report_blocks.append(block)
                
        except: continue

    # ✅ まとめて通知
    if report_blocks:
        header = f"📢 **【Jack株AI：チャンス到来レポート】** ({get_jst_now().strftime('%H:%M')})\n"
        footer = f"\n🕙 監視時間: {MONITOR_START} ～ {MONITOR_END}"
        full_msg = header + "━━━━━━━━━━━━━━━━━━\n" + "\n".join(report_blocks) + "━━━━━━━━━━━━━━━━━━" + footer
        requests.post(DISCORD_WEBHOOK_URL, json={"content": full_msg})
    else:
        print(f"[{get_jst_now().strftime('%H:%M')}] 監視中：条件に合う銘柄なし")

# (以下、run_prime_prescan や mainループは以前と同様)
