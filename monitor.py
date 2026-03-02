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

# 監視スケジュール設定
START_TIME_STR = "09:20"
END_TIME_STR = "15:10"

def get_jst_now():
    """日本標準時を取得"""
    return datetime.now(timezone(timedelta(hours=9)))

def is_market_open():
    """日本の取引時間内かどうかを判定"""
    now = get_jst_now()
    if now.weekday() >= 5: return False # 土日は停止
    
    current_time = now.time()
    # 前場・後場を合わせた監視時間
    morning_session = (dt_time(9, 20) <= current_time <= dt_time(11, 30))
    afternoon_session = (dt_time(12, 40) <= current_time <= dt_time(15, 10))
    return morning_session or afternoon_session

def send_to_discord(message):
    """Discordにメッセージを送信"""
    payload = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"通知エラー: {e}")

def get_prediction_logic(close, volume, ma60, ma200):
    """出来高急増(2.5倍以上)とMAの傾きによる推移予測"""
    s60 = ma60.diff(20).iloc[-1]
    s200 = ma200.diff(20).iloc[-1]
    
    avg_vol = volume.tail(30).mean()
    current_vol = volume.iloc[-1]
    vol_ratio = (current_vol / avg_vol) if avg_vol > 0 else 0
    is_vol_spike = vol_ratio >= 2.5
    
    spike_text = f"🔥 **【出来高急増】平時の{vol_ratio:.1f}倍！大口参入の兆候**" if is_vol_spike else ""
    
    if s60 > 0 and s200 > 0:
        pred = "📈 **上昇トレンド継続予測**: 買いの勢いが非常に強いです。"
    elif s60 < 0 and s200 < 0:
        pred = "📉 **下落トレンド継続予測**: 下げ圧力が強く、まだ底打ちしていません。"
    elif s60 > 0 and s200 < 0:
        pred = "🔄 **反転・リバウンド予測**: 短期的な買い戻しが期待できるポイント。"
    else:
        pred = "☁️ **方向感の探り合い**: 現在はレンジ内。ブレイクを待つのが賢明です。"
        
    return f"{spike_text}\n{pred}"

def monitor_cycle():
    """監視と通知のメインサイクル"""
    if not os.path.exists(WATCHLIST_FILE): return
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if not watchlist: return

    for item in watchlist:
        ticker = item['ticker']
        name_jp = item.get('name', '銘柄名不明') # 和名の取得
        
        try:
            df = yf.download(ticker, period="2d", interval="1m", progress=False)
            if df.empty: continue
            
            close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
            volume = df['Volume'].iloc[:, 0] if isinstance(df['Volume'], pd.DataFrame) else df['Volume']
            high = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']
            low = df['Low'].iloc[:, 0] if isinstance(df['Low'], pd.DataFrame) else df['Low']

            ma60 = close.rolling(60).mean()
            ma200 = close.rolling(200).mean()
            ma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            bb_u2 = ma20 + (std20 * 2)
            bb_l2 = ma20 - (std20 * 2)

            now_p = close.iloc[-1]
            sigs = []
            if now_p > ma60.iloc[-1] and (high.tail(15) >= bb_u2.tail(15)).sum() >= 3:
                sigs.append("法則1: 天井圏での売り検討サイン")
            if now_p < ma60.iloc[-1] and (low.tail(15) <= bb_l2.tail(15)).sum() >= 3:
                sigs.append("法則7: 底打ち圏での買い検討サイン")
            
            is_strong = (ma60.diff(20).iloc[-1] * ma200.diff(20).iloc[-1] > 0)
            prediction = get_prediction_logic(close, volume, ma60, ma200)

            # --- メッセージ構築 ---
            msg = f"━━━━━━━━━━━━━━━━━━\n"
            msg += f"📢 **【Jack株AI：5分定時予測】**\n"
            msg += f"銘柄: **{name_jp} ({ticker})**\n"
            msg += f"現在値: `{now_p:,.1f}円` (時刻: {get_jst_now().strftime('%H:%M')})\n"
            msg += f"🕙 **監視時間: {START_TIME_STR} ～ {END_TIME_STR} (日本時間)**\n"
            
            if sigs:
                msg += "\n" + "\n".join([f"⚠️ {s}" for s in sigs]) + "\n"
            if is_strong:
                msg += "💎 **【法則8確定】強い方向性トレンド発生中**\n"
            
            msg += f"\n{prediction}\n"
            msg += f"━━━━━━━━━━━━━━━━━━"
            
            send_to_discord(msg)
            
        except Exception as e:
            print(f"Error {ticker}: {e}")

if __name__ == "__main__":
    print(f"🚀 Monitoring System Active (JST: {START_TIME_STR}-{END_TIME_STR})")
    # 運用開始メッセージ
    send_to_discord(f"✅ **システム稼働開始（{get_jst_now().strftime('%m/%d')}）**\n本日の監視スケジュール: **{START_TIME_STR} ～ {END_TIME_STR} (日本時間)**\n和名表示および予測機能が有効です。")
    
    while True:
        if is_market_open():
            monitor_cycle()
            time.sleep(300) # 5分待機
        else:
            time.sleep(60)

