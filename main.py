import yfinance as yf
import pandas as pd
import requests
import json
from datetime import datetime, timedelta, timezone
import os

# ==========================================
# ⚙️ 設定エリア
# ==========================================
DISCORD_WEBHOOK_URL = "ここにあなたのDiscordウェブフックURLを貼り付けてください"

# 監視対象
WATCH_LIST = {
    "6098.T": "リクルート",
    "6758.T": "ソニーG",
    "9984.T": "SBG",
    "7203.T": "トヨタ",
    "8306.T": "三菱UFJ",
    "6861.T": "キーエンス"
}

# ==========================================
# 🧠 テクニカル分析ロジック (3分足生成 & 予兆検知)
# ==========================================

def resample_to_3min(df_1m):
    """1分足データを3分足に変換する"""
    # 3分ごとにまとめる
    df_3m = df_1m.resample('3min').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna()
    return df_3m

def calculate_indicators(df):
    """MACDとRSIを計算"""
    close = df['Close']
    
    # RSI (14期間)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain/loss))
    
    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    
    df['RSI'] = rsi
    df['MACD'] = macd
    df['Signal'] = signal
    df['Hist'] = hist
    
    return df

def check_signals(code, name):
    try:
        # 1分足を5日分取得 (3分足を作るために十分な量)
        stock = yf.Ticker(code)
        df_1m = stock.history(period="5d", interval="1m")
        
        if df_1m.empty: return None

        # 3分足に変換
        df = resample_to_3min(df_1m)
        df = calculate_indicators(df)

        # 最新とその1つ前のデータ
        now = df.iloc[-1]
        prev = df.iloc[-2]

        # --- 判定ロジック ---
        signals = []

        # 1. 🔮 MACDクロス予兆 (Pre-Cross)
        # 条件: MACDはまだシグナルより下だが、ヒストグラムが縮小(改善)しており、かつRSIが上向いている
        macd_improving = (now['Hist'] < 0) and (now['Hist'] > prev['Hist']) # まだマイナスだが幅が縮まっている
        rsi_rising = (now['RSI'] > prev['RSI']) and (now['RSI'] < 60) # RSIが上昇中かつ過熱していない
        
        if macd_improving and rsi_rising:
            # クロス直前判定（ヒストグラムが0に近い）
            if now['Hist'] > -2.0: # ※銘柄の価格帯によりますが、0に近づいているか
                signals.append(f"⚡ MACDクロス直前 (RSI:{now['RSI']:.1f})")

        # 2. 🕯️ 強いローソク足パターン (包み足)
        is_bullish_engulfing = (prev['Close'] < prev['Open']) and \
                               (now['Close'] > now['Open']) and \
                               (now['Open'] < prev['Close']) and \
                               (now['Close'] > prev['Open'])
        if is_bullish_engulfing:
            signals.append("🔥 陽の包み足 (強い買い)")

        # 3. ゴールデンクロス確定 (確認用)
        if (prev['Hist'] < 0) and (now['Hist'] > 0):
            signals.append("✅ MACDゴールデンクロス発生")

        if signals:
            return f"**{name} ({code.replace('.T','')})** [3分足]\n" + "\n".join(signals) + f"\n現在値: {int(now['Close'])}円"
        
        return None

    except Exception as e:
        print(f"Error {code}: {e}")
        return None

def job():
    messages = []
    for code, name in WATCH_LIST.items():
        msg = check_signals(code, name)
        if msg: messages.append(msg)
            
    if messages:
        full_msg = "🦅 **AI株価監視 (3分足ロジック)**\n" + "\n".join(messages)
        requests.post(DISCORD_WEBHOOK_URL, json={"content": full_msg})
        print("通知送信完了")
    else:
        print("シグナルなし")

# ==========================================
# 🚀 実行制御 (時間指定)
# ==========================================
if __name__ == "__main__":
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)
    current_time = now.strftime("%H:%M")
    
    print(f"現在時刻(JST): {current_time}")

    # 指定された監視時間帯の設定
    # 前場: 09:00 - 11:10
    # 後場: 12:30 - 14:50
    is_market_open = ("09:00" <= current_time <= "11:10") or \
                     ("12:30" <= current_time <= "14:50")

    # 曜日の確認 (月=0, 金=4)
    if now.weekday() <= 4 and is_market_open:
        print("🔍 監視条件合致。スキャン開始...")
        job()
    else:
        print("💤 監視時間外です。")
