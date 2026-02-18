import yfinance as yf
import pandas as pd
import requests
import json
import time
from datetime import datetime, timedelta, timezone

# ==========================================
# ⚙️ 設定エリア
# ==========================================
DISCORD_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
SHEET_ID = "1eNQr-uOb97YQsegYzQsegYzQsegYzQsegYz"

# ==========================================
# 🧠 銘柄リスト取得
# ==========================================
def get_watch_list():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
        df = pd.read_csv(url)
        watch_dict = {}
        for index, row in df.iterrows():
            name = str(row.iloc[2]) if len(row) > 2 else "銘柄"
            code_day = str(row.iloc[0])
            if code_day != "nan" and code_day.replace('.','').isdigit():
                code = code_day.split('.')[0] + ".T"
                watch_dict[code] = f"{name} (Day)"
            code_swing = str(row.iloc[1])
            if code_swing != "nan" and code_swing.replace('.','').isdigit():
                code = code_swing.split('.')[0] + ".T"
                watch_dict[code] = watch_dict.get(code, name) + " (Swing)"
        return watch_dict
    except:
        return {"9984.T": "SBG", "7203.T": "トヨタ"}

# ==========================================
# 📊 テクニカル分析
# ==========================================
def calculate_indicators(df):
    close = df['Close']
    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain/loss))
    # MACD
    df['MACD'] = close.ewm(span=12).mean() - close.ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    return df

def send_discord(message):
    payload = {"username": "株監視AI教授 📈", "content": message}
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

def check_signals():
    watch_list = get_watch_list()
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime('%H:%M')
    
    print(f"⏰ {now} 監視フェーズ開始...")
    
    for code, name in watch_list.items():
        try:
            stock = yf.Ticker(code)
            df = stock.history(period="1d", interval="1m")
            if df.empty or len(df) < 30: continue
            
            # 3分足へリサンプル
            df_3m = df.resample('3min').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            df_3m = calculate_indicators(df_3m)
            
            last = df_3m.iloc[-1]
            prev = df_3m.iloc[-2]
            
            # --- サイン判定ロジック ---
            alert = ""
            # 1. MACD ゴールデンクロス
            if prev['Hist'] < 0 and last['Hist'] > 0:
                alert = "🚀【MACDゴールデンクロス】上昇の初動を検知！"
            # 2. RSI売られすぎからの反発
            elif last['RSI'] < 30:
                alert = "⚡【RSI売られすぎ】反発の臨界点に到達！"
            
            if alert:
                msg = f"🔔 **{name} ({code})**\n⏰ {now}\n💰 現在値: {last['Close']:.1f}円\n📊 {alert}\n📈 RSI: {last['RSI']:.1f}"
                send_discord(msg)
                print(f"✅ {code} サイン送信")
                
        except Exception as e:
            print(f"❌ {code} エラー: {e}")

if __name__ == "__main__":
    check_signals()
