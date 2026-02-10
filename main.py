import os
import yfinance as yf
import pandas as pd
import requests
import json
import datetime
import time

# ==========================================
# ⚙️ 設定 (GitHub Secrets)
# ==========================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_URL")
SHEET_ID = os.environ.get("SHEET_ID")

# ==========================================
# 🛠️ 共通関数
# ==========================================
def get_watch_lists():
    """スプレッドシートからデイトレ用(A列)とスイング用(B列)を読み込む"""
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
        df = pd.read_csv(url, header=None, dtype=str).fillna("")
        
        day_tickers = []
        swing_tickers = []

        # 2行目(index 1)以降を読み込む（1行目はヘッダー想定）
        if len(df) > 1:
            # A列: デイトレ
            raw_day = df.iloc[1:, 0].tolist()
            for t in raw_day:
                t = str(t).strip()
                if t.isdigit(): day_tickers.append(f"{t}.T")
                elif t: day_tickers.append(t)
            
            # B列: スイング（B列が存在する場合）
            if len(df.columns) > 1:
                raw_swing = df.iloc[1:, 1].tolist()
                for t in raw_swing:
                    t = str(t).strip()
                    if t.isdigit(): swing_tickers.append(f"{t}.T")
                    elif t: swing_tickers.append(t)
        
        return day_tickers, swing_tickers
    except Exception as e:
        print(f"Sheet Error: {e}")
        return [], []

def send_discord(msg, title="通知"):
    if not DISCORD_WEBHOOK_URL: return
    data = {"content": f"{title} {msg}"}
    requests.post(DISCORD_WEBHOOK_URL, headers={"Content-Type": "application/json"}, data=json.dumps(data))

def calc_indicators(df):
    """RSIとMACDを計算する"""
    if len(df) < 26: return df
    
    # RSI (14)
    close = df['Close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain/loss))

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    return df

def generate_3min_candles(df_1m):
    """1分足から3分足を生成する"""
    # 3分ごとにリサンプリング
    df_3m = df_1m.resample('3T').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna()
    return df_3m

# ==========================================
# 🐇 デイトレ監視ロジック (3分足)
# ==========================================
def check_day_trade(tickers):
    if not tickers: return []
    print(f"🐇 デイトレ監視開始: {len(tickers)}銘柄")
    msgs = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            # 1分足を直近取得して、3分足を作る
            # ※yfinanceには3mがないため、1mを取得して合成する
            hist = stock.history(period="1d", interval="1m")
            
            if len(hist) < 30: continue
            
            # 3分足生成
            df = generate_3min_candles(hist)
            if len(df) < 26: continue

            # 指標計算
            df = calc_indicators(df)
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            price_str = f"{curr['Close']:,.0f}"

            # --- 判定 ---
            # 1. MACD ゴールデンクロス/デッドクロス
            if prev['MACD'] < prev['SIGNAL'] and curr['MACD'] > curr['SIGNAL']:
                msgs.append(f"🚀 **{ticker} (3分足)** MACDゴールデンクロス ({price_str}円)")
            elif prev['MACD'] > prev['SIGNAL'] and curr['MACD'] < curr['SIGNAL']:
                msgs.append(f"💀 **{ticker} (3分足)** MACDデッドクロス ({price_str}円)")

            # 2. RSI シグナル (敏感に反応させるため 25/75)
            if curr['RSI'] <= 25:
                msgs.append(f"✨ **{ticker} (3分足)** 買い時 RSI:{curr['RSI']:.1f} ({price_str}円)")
            elif curr['RSI'] >= 75:
                msgs.append(f"📉 **{ticker} (3分足)** 売り時 RSI:{curr['RSI']:.1f} ({price_str}円)")

        except Exception as e:
            print(f"Err Day {ticker}: {e}")
            
    return msgs

# ==========================================
# 🐢 スイング監視ロジック (日足 & 30分足)
# ==========================================
def check_swing_trade(tickers):
    if not tickers: return []
    
    # 時間制御: 前場(11:00-11:30) と 後場(14:30-15:00) の間のみ実行
    # ※GitHub Actionsの時刻ズレも考慮し、幅を持たせています
    JST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(JST)
    current_time = now.strftime('%H:%M')
    
    # チェックすべき時間帯か？
    is_morning_check = ("11:00" <= current_time <= "11:35")
    is_afternoon_check = ("14:30" <= current_time <= "15:05")

    if not (is_morning_check or is_afternoon_check):
        print(f"💤 スイング監視対象外の時間です ({current_time})")
        return []

    print(f"🐢 スイング監視開始 ({current_time}): {len(tickers)}銘柄")
    msgs = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            
            # --- 日足チェック ---
            hist_d = stock.history(period="6mo", interval="1d")
            hist_d = calc_indicators(hist_d)
            curr_d = hist_d.iloc[-1]
            prev_d = hist_d.iloc[-2]

            # --- 30分足チェック ---
            hist_30m = stock.history(period="5d", interval="30m")
            hist_30m = calc_indicators(hist_30m)
            curr_30 = hist_30m.iloc[-1]
            prev_30 = hist_30m.iloc[-2]
            
            price_str = f"{curr_d['Close']:,.0f}"

            # 判定ロジック (日足と30分足の複合条件など自由に設定可)
            
            # 日足 MACD/RSI
            if prev_d['MACD'] < prev_d['SIGNAL'] and curr_d['MACD'] > curr_d['SIGNAL']:
                msgs.append(f"🌊 **{ticker} (日足)** MACDゴールデンクロス ({price_str}円)")
            if curr_d['RSI'] <= 30:
                msgs.append(f"💎 **{ticker} (日足)** RSI底値圏: {curr_d['RSI']:.1f}")

            # 30分足 MACD
            if prev_30['MACD'] < prev_30['SIGNAL'] and curr_30['MACD'] > curr_30['SIGNAL']:
                msgs.append(f"🌊 **{ticker} (30分足)** MACD好転 ({price_str}円)")

        except Exception as e:
            print(f"Err Swing {ticker}: {e}")

    return msgs

# ==========================================
# 🚀 メイン実行
# ==========================================
def main():
    day_list, swing_list = get_watch_lists()
    
    # デイトレは毎回チェック
    day_msgs = check_day_trade(day_list)
    if day_msgs:
        send_discord("\n".join(day_msgs), "🐇【デイトレ】")
    
    # スイングは時間限定チェック
    swing_msgs = check_swing_trade(swing_list)
    if swing_msgs:
        send_discord("\n".join(swing_msgs), "🐢【スイング】")
        
    if not day_msgs and not swing_msgs:
        print("No signals.")

if __name__ == "__main__":
    main()
