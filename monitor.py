import yfinance as yf
import pandas as pd
import requests
import json
import os
import time
from datetime import datetime, timedelta, timezone, time as dt_time

# --- ⚙️ 設定エリア ---
# ご指定いただいたDiscord Webhook URLを組み込みました
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"

def get_jst_now():
    """日本標準時を取得"""
    return datetime.now(timezone(timedelta(hours=9)))

def is_market_open():
    """
    日本の取引時間内かどうかを判定
    前場: 09:20 - 11:30
    後場: 12:40 - 15:10
    """
    now = get_jst_now()
    # 土日は動作停止
    if now.weekday() >= 5:
        return False
    
    current_time = now.time()
    morning_session = (dt_time(9, 20) <= current_time <= dt_time(11, 30))
    afternoon_session = (dt_time(12, 40) <= current_time <= dt_time(15, 10))
    
    return morning_session or afternoon_session

def send_to_discord(message):
    """Discordにメッセージを送信"""
    payload = {"content": message}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 204:
            print(f"[{get_jst_now().strftime('%H:%M')}] Discord送信成功")
        else:
            print(f"Discord送信失敗: {response.status_code}")
    except Exception as e:
        print(f"通知エラー: {e}")

def get_prediction_logic(close, volume, ma60, ma200):
    """出来高急増とMAの傾きを加味した推移予測 (法則8の拡張)"""
    # 20分間のMAの傾き
    s60 = ma60.diff(20).iloc[-1]
    s200 = ma200.diff(20).iloc[-1]
    
    # 出来高急増判定（直近30分平均の2.5倍以上）
    avg_vol = volume.tail(30).mean()
    current_vol = volume.iloc[-1]
    is_vol_spike = (current_vol > (avg_vol * 2.5)) if avg_vol > 0 else False
    
    spike_text = "🔥 **【出来高急増】大口参入・トレンド加速の兆候！**" if is_vol_spike else ""
    
    # 予測アルゴリズム
    if s60 > 0 and s200 > 0:
        pred = "📈 **上昇強気継続予測**: 非常に強い流れです。押し目買い優勢。"
    elif s60 < 0 and s200 < 0:
        pred = "📉 **下落弱気継続予測**: 売り圧力が強く、まだ下げ止まっていません。"
    elif s60 > 0 and s200 < 0:
        pred = "🔄 **反転・リバウンド予測**: 短期的な買い戻しが入るポイントです。"
    else:
        pred = "☁️ **保ち合い予測**: 方向感を探る動き。ブレイク待ちの状態です。"
        
    return f"{spike_text}\n{pred}"

def monitor_cycle():
    """監視と通知の1サイクル"""
    if not os.path.exists(WATCHLIST_FILE):
        return

    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)

    if not watchlist:
        return

    for item in watchlist:
        ticker = item['ticker']
        try:
            # 1分足データを取得
            df = yf.download(ticker, period="2d", interval="1m", progress=False)
            if df.empty: continue
            
            # データの抽出
            close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
            volume = df['Volume'].iloc[:, 0] if isinstance(df['Volume'], pd.DataFrame) else df['Volume']
            high = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']
            low = df['Low'].iloc[:, 0] if isinstance(df['Low'], pd.DataFrame) else df['Low']

            # 各種指標の計算
            ma60 = close.rolling(60).mean()
            ma200 = close.rolling(200).mean()
            ma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            bb_u2 = ma20 + (std20 * 2)
            bb_l2 = ma20 - (std20 * 2)

            # 法則判定
            sigs = []
            now_p = close.iloc[-1]
            
            # 法則1 & 7 (BB接触)
            if now_p > ma60.iloc[-1] and (high.tail(15) >= bb_u2.tail(15)).sum() >= 3:
                sigs.append("法則1: 天井圏・売り検討")
            if now_p < ma60.iloc[-1] and (low.tail(15) <= bb_l2.tail(15)).sum() >= 3:
                sigs.append("法則7: 底打ち圏・買い検討")
            
            # 法則8 (20分タイムラグ確定)
            is_strong_trend = (ma60.diff(20).iloc[-1] * ma200.diff(20).iloc[-1] > 0)

            # 予測レポートの生成
            prediction = get_prediction_logic(close, volume, ma60, ma200)

            # メッセージの組み立て
            msg = f"━━━━━━━━━━━━━━\n"
            msg += f"🔔 **【5分定時予測レポート】**\n"
            msg += f"銘柄: **{ticker}**\n"
            msg += f"現在値: `{now_p:,.1f}円` ({get_jst_now().strftime('%H:%M')})\n"
            
            if sigs:
                msg += "\n" + "\n".join([f"⚠️ {s}" for s in sigs]) + "\n"
            
            if is_strong_trend:
                msg += "💎 **【法則8確定】強い方向性トレンド発生中**\n"
            
            msg += f"\n{prediction}\n"
            msg += f"━━━━━━━━━━━━━━"
            
            send_to_discord(msg)
            
        except Exception as e:
            print(f"Error {ticker}: {e}")

if __name__ == "__main__":
    print(f"🚀 Monitoring System Active (Schedule: 09:20-15:10)")
    while True:
        # 取引時間内のみ稼働
        if is_market_open():
            print(f"Running monitor cycle at {get_jst_now().strftime('%H:%M')}...")
            monitor_cycle()
            time.sleep(300) # 5分待機
        else:
            # 時間外は1分ごとに開場をチェック
            time.sleep(60)

