import yfinance as yf
import pandas as pd
import requests
import json
import sys  # プログラム終了用
import time
from datetime import datetime, timedelta, timezone

# ==========================================
# ⚙️ 設定エリア
# ==========================================
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1472281747000393902/Fbclh0R3R55w6ZnzhenJ24coaUPKy42abh3uPO-fRjfQulk9OwAq-Cf8cJQOe2U4SFme"
SHEET_ID = "1eNQr-uOb97YQsegYzQsegYzQsegYzQsegYz"

COOLDOWN_MINUTES = 60
last_sent = {}

# ==========================================
# 🕒 時間判定ロジック
# ==========================================
def is_market_open(now_dt):
    if now_dt.weekday() >= 5: return False # 土日
    
    current_time = now_dt.strftime('%H:%M')
    # 前場: 09:00 〜 11:50 / 後場: 12:30 〜 14:50
    if "09:00" <= current_time <= "11:50": return True
    if "12:30" <= current_time <= "14:50": return True
    return False

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
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain/loss))
    df['MACD'] = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    return df

def send_discord(message):
    payload = {"username": "株監視AI教授 📈", "content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"Discord送信エラー: {e}")

def check_signals():
    global last_sent
    watch_list = get_watch_list()
    jst = timezone(timedelta(hours=9))
    now_dt = datetime.now(jst)
    now_str = now_dt.strftime('%H:%M')
    
    print(f"⏰ {now_str} スキャン実行中...")
    
    for code, name in watch_list.items():
        if code in last_sent:
            elapsed = (now_dt - last_sent[code]).total_seconds() / 60
            if elapsed < COOLDOWN_MINUTES: continue

        try:
            stock = yf.Ticker(code)
            df = stock.history(period="1d", interval="1m")
            if df.empty or len(df) < 30: continue
            
            df_3m = df.resample('3min').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            df_3m = calculate_indicators(df_3m)
            
            last = df_3m.iloc[-1]
            prev = df_3m.iloc[-2]
            
            alert = ""
            if prev['Hist'] < 0 and last['Hist'] > 0:
                alert = "🚀【MACDゴールデンクロス】"
            elif last['RSI'] < 30:
                alert = "⚡【RSI売られすぎ】"
            
            if alert:
                msg = f"🔔 **{name} ({code})**\n⏰ {now_str}\n💰 現在値: {last['Close']:.1f}円\n📊 {alert}\n📈 RSI: {last['RSI']:.1f}"
                send_discord(msg)
                last_sent[code] = now_dt
                print(f"✅ {code} 通知済み")
        except:
            continue

# ==========================================
# 🚀 メイン実行ループ
# ==========================================
if __name__ == "__main__":
    jst = timezone(timedelta(hours=9))
    now_dt = datetime.now(jst)
    
    print("------------------------------------------")
    print(f"🤖 システム起動時刻: {now_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print("------------------------------------------")

    # 起動時の時間外チェック
    if not is_market_open(now_dt):
        msg = f"⚠️ 【動作確認】市場時間外（または休日）に起動されました。\n接続テスト成功です。15秒後に自動停止します。"
        print(msg)
        send_discord(msg)
        
        time.sleep(15)  # 15秒待機
        print("🛑 停止します。")
        sys.exit() # プログラム終了

    # 市場時間内の場合は通常ループ
    print("✅ 市場稼働時間内です。常駐監視を開始します。")
    while True:
        current_now = datetime.now(jst)
        if is_market_open(current_now):
            check_signals()
            time.sleep(180) # 3分おき
        else:
            print(f"😴 市場が終了しました ({current_now.strftime('%H:%M')})。終了します。")
            send_discord("📢 市場時間が終了したため、本日の監視を終了し停止します。")
            sys.exit()
