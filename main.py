import yfinance as yf
import pandas as pd
import requests
import json
import time
from datetime import datetime, timedelta, timezone

# ==========================================
# ⚙️ 設定エリア（組み込み済み）
# ==========================================
DISCORD_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
SHEET_ID = "1eNQr-uOb97YQsegYzQsegYzQsegYzQsegYz"

# 通知の間隔（分）: 同じ銘柄は60分間通知しない
COOLDOWN_MINUTES = 60
last_sent = {}

# ==========================================
# 🕒 時間判定ロジック
# ==========================================
def is_market_open(now_dt):
    # 土日 (5=土曜日, 6=日曜日) は動かさない
    if now_dt.weekday() >= 5:
        return False
    
    # 時刻を "HH:MM" 形式で取得
    current_time = now_dt.strftime('%H:%M')
    
    # 前場: 09:00 〜 11:50
    if "09:00" <= current_time <= "11:50":
        return True
    # 後場: 12:30 〜 14:50
    if "12:30" <= current_time <= "14:50":
        return True
        
    return False

# ==========================================
# 🧠 銘柄リスト取得
# ==========================================
def get_watch_list():
    try:
        # スプレッドシートをCSV形式で取得
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
        df = pd.read_csv(url)
        watch_dict = {}
        for index, row in df.iterrows():
            name = str(row.iloc[2]) if len(row) > 2 else "銘柄"
            # 1列目: デイトレ用
            code_day = str(row.iloc[0])
            if code_day != "nan" and code_day.replace('.','').isdigit():
                code = code_day.split('.')[0] + ".T"
                watch_dict[code] = f"{name} (Day)"
            # 2列目: スイング用
            code_swing = str(row.iloc[1])
            if code_swing != "nan" and code_swing.replace('.','').isdigit():
                code = code_swing.split('.')[0] + ".T"
                watch_dict[code] = watch_dict.get(code, name) + " (Swing)"
        return watch_dict
    except Exception as e:
        print(f"⚠️ スプレッドシート読み込みエラー: {e}")
        return {"9984.T": "SBG", "7203.T": "トヨタ"}

# ==========================================
# 📊 テクニカル分析
# ==========================================
def calculate_indicators(df):
    close = df['Close']
    # RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain/loss))
    # MACD
    df['MACD'] = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    return df

def send_discord(message):
    payload = {"username": "株監視AI教授 📈", "content": message}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        return response.status_code == 204
    except:
        return False

def check_signals():
    global last_sent
    watch_list = get_watch_list()
    jst = timezone(timedelta(hours=9))
    now_dt = datetime.now(jst)
    now_str = now_dt.strftime('%H:%M')
    
    print(f"⏰ {now_str} 全 {len(watch_list)} 銘柄をスキャン中...")
    
    for code, name in watch_list.items():
        # クールダウンチェック
        if code in last_sent:
            elapsed = (now_dt - last_sent[code]).total_seconds() / 60
            if elapsed < COOLDOWN_MINUTES:
                continue

        try:
            stock = yf.Ticker(code)
            # 1分足を取得
            df = stock.history(period="1d", interval="1m")
            if df.empty or len(df) < 30: continue
            
            # 3分足へ変換
            df_3m = df.resample('3min').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
            df_3m = calculate_indicators(df_3m)
            
            last = df_3m.iloc[-1]
            prev = df_3m.iloc[-2]
            
            alert = ""
            # ロジック1: MACDゴールデンクロス
            if prev['Hist'] < 0 and last['Hist'] > 0:
                alert = "🚀【MACDゴールデンクロス】上昇の初動を検知！"
            # ロジック2: RSI売られすぎ
            elif last['RSI'] < 30:
                alert = "⚡【RSI売られすぎ】反発の臨界点に到達！"
            
            if alert:
                msg = f"🔔 **{name} ({code})**\n⏰ {now_str}\n💰 現在値: {last['Close']:.1f}円\n📊 {alert}\n📈 RSI: {last['RSI']:.1f}"
                if send_discord(msg):
                    last_sent[code] = now_dt
                    print(f"✅ {code} 通知送信完了")
                
        except Exception as e:
            print(f"❌ {code} 分析エラー: {e}")

# ==========================================
# 🚀 メイン実行ループ
# ==========================================
if __name__ == "__main__":
    print("🤖 株監視システム（自動運用モード）を起動しました。")
    jst = timezone(timedelta(hours=9))
    
    while True:
        now_dt = datetime.now(jst)
        
        if is_market_open(now_dt):
            check_signals()
            # 稼働中は3分（180秒）待機
            time.sleep(180)
        else:
            current_time = now_dt.strftime('%H:%M')
            # 週末または時間外
            if now_dt.weekday() >= 5:
                status = "週末休み"
            else:
                status = "市場時間外"
            
            print(f"😴 {status} です ({current_time})。待機中...")
            # 1分おきに時刻を再確認
            time.sleep(60)
