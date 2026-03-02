import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime, timedelta, timezone

# --- ⚙️ 設定エリア ---
# DiscordのWebhook URLをここに貼り付けてください
DISCORD_WEBHOOK_URL = "ここにURLを貼り付け"
WATCHLIST_FILE = "jack_watchlist.json"

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_to_discord(message):
    """Discordにメッセージを送信する"""
    payload = {"content": message}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 204:
            print("Successfully sent to Discord.")
        else:
            print(f"Failed to send: {response.status_code}")
    except Exception as e:
        print(f"Error sending to Discord: {e}")

def get_prediction_logic(close, volume, ma60, ma200):
    """
    株価の動きを予測するロジック (法則8の拡張)
    出来高の急増（平時の2.5倍以上）を検知
    """
    # 傾き計算
    s60 = ma60.diff(20).iloc[-1]
    s200 = ma200.diff(20).iloc[-1]
    
    # 出来高急増判定
    avg_vol = volume.tail(30).mean() # 直近30分平均
    current_vol = volume.iloc[-1]
    is_vol_spike = current_vol > (avg_vol * 2.5)
    
    spike_text = "🔥 **【出来高急増】大口の参入を検知！**" if is_vol_spike else ""
    
    # 予測アルゴリズム
    if s60 > 0 and s200 > 0:
        pred = "📈 **上昇強気継続予測**: 強いトレンドに乗っています。目標値までホールド推奨。"
    elif s60 < 0 and s200 < 0:
        pred = "📉 **下落弱気継続予測**: まだ底が見えません。反発を確認するまで静観が安全です。"
    elif s60 > 0 and s200 < 0:
        pred = "🔄 **反転の予兆**: 長期線付近での攻防です。短期的なリバウンドのチャンス。"
    else:
        pred = "☁️ **方向感の探り合い**: 現在は保ち合い状態です。ブレイクを待ちましょう。"
        
    return f"{spike_text}\n{pred}"

def monitor_cycle():
    """5分ごとの監視メイン処理"""
    if not os.path.exists(WATCHLIST_FILE):
        print("Watchlist file not found. Waiting...")
        return

    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)

    if not watchlist:
        print("Watchlist is empty.")
        return

    for item in watchlist:
        ticker = item['ticker']
        try:
            # 1分足データを取得
            df = yf.download(ticker, period="2d", interval="1m", progress=False)
            if df.empty: continue
            
            # yfinanceの構造変更に対応
            close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
            volume = df['Volume'].iloc[:, 0] if isinstance(df['Volume'], pd.DataFrame) else df['Volume']
            high = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']
            low = df['Low'].iloc[:, 0] if isinstance(df['Low'], pd.DataFrame) else df['Low']

            # 指標計算
            ma60 = close.rolling(60).mean()
            ma200 = close.rolling(200).mean()
            ma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            bb_u2 = ma20 + (std20 * 2)
            bb_l2 = ma20 - (std20 * 2)

            # 法則判定
            sigs = []
            now_price = close.iloc[-1]
            
            # 法則1 & 7 (BB接触)
            if now_price > ma60.iloc[-1] and (high.tail(15) >= bb_u2.tail(15)).sum() >= 3:
                sigs.append("法則1: 天井圏での売り検討サイン")
            if now_price < ma60.iloc[-1] and (low.tail(15) <= bb_l2.tail(15)).sum() >= 3:
                sigs.append("法則7: 底打ち圏での買い検討サイン")
            
            # 法則8 (20分タイムラグ確定)
            is_strong_trend = (ma60.diff(20).iloc[-1] * ma200.diff(20).iloc[-1] > 0)

            # 予測情報の生成
            prediction_text = get_prediction_logic(close, volume, ma60, ma200)

            # --- Discordメッセージ構築 ---
            msg = f"━━━━━━━━━━━━━━\n"
            msg += f"🔔 **【5分定時監視レポート】**\n"
            msg += f"銘柄: **{ticker}**\n"
            msg += f"現在値: `{now_price:,.1f}円` (時刻: {get_jst_now().strftime('%H:%M')})\n\n"
            
            if sigs:
                msg += "⚠️ **合致した黄金法則:**\n" + "\n".join([f"・{s}" for s in sigs]) + "\n"
            
            if is_strong_trend:
                msg += "💎 **【法則8確定】強い方向性が発生しています**\n"
            
            msg += f"\n{prediction_text}\n"
            msg += f"━━━━━━━━━━━━━━"
            
            send_to_discord(msg)
            
        except Exception as e:
            print(f"Error scanning {ticker}: {e}")

if __name__ == "__main__":
    print(f"🚀 Monitoring started. (Cycle: 5 minutes)")
    while True:
        monitor_cycle()
        time.sleep(300) # 300秒 = 5分待機
