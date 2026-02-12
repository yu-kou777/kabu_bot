import yfinance as yf
import pandas as pd
import requests
import json
from datetime import datetime, timedelta, timezone

# ==========================================
# ⚙️ 設定エリア
# ==========================================
# DiscordのURL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

# ★ここにスプレッドシートIDを入力してください
# (URLが https://docs.google.com/spreadsheets/d/abc12345/edit なら "abc12345" がID)
SHEET_ID = "1eNQr-uOb97YQsegYzQsegYzQsegYzQsegYz"  # ←ここをあなたのIDに書き換えてください！

# ==========================================
# 🧠 シート読み込み & 監視リスト作成
# ==========================================
def get_watch_list():
    """1eNqR-uOb97YQsegYzQ_1y7b4ofsQE1zilu_jN2_0l8A"""
    print("📋 スプレッドシートから設定を読み込み中...")
    try:
        # CSVとしてダウンロードするURLを作成
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
        
        # データを読み込む
        df = pd.read_csv(url)
        
        # カラム名を整理（画像に合わせて A:デイトレ, B:スイング, C:銘柄名 と仮定）
        # ※実際のカラム名に合わせて調整してください。ここでは1行目の名前を使います。
        
        watch_dict = {}

        # 行ごとに処理
        for index, row in df.iterrows():
            name = str(row.iloc[2]) if len(row) > 2 else "不明" # C列: 銘柄名
            if name == "nan" or name == "-": name = "銘柄"

            # A列: デイトレ銘柄
            code_day = str(row.iloc[0])
            if code_day != "nan" and code_day.replace('.','').isdigit():
                code = code_day.split('.')[0] + ".T"
                watch_dict[code] = f"{name} (Day)"

            # B列: スイング銘柄
            code_swing = str(row.iloc[1])
            if code_swing != "nan" and code_swing.replace('.','').isdigit():
                code = code_swing.split('.')[0] + ".T"
                # すでに登録済みなら情報を追記
                if code in watch_dict:
                    watch_dict[code] = f"{name} (Day/Swing)"
                else:
                    watch_dict[code] = f"{name} (Swing)"

        print(f"✅ 監視リスト作成完了: {len(watch_dict)}銘柄")
        return watch_dict

    except Exception as e:
        print(f"❌ シート読み込みエラー: {e}")
        # 読み込めなかった場合の緊急用リスト
        return {"9984.T": "SBG(Backup)", "7203.T": "トヨタ(Backup)"}

# ==========================================
# 🧠 テクニカル分析ロジック (3分足生成 & 予兆検知)
# ==========================================
def resample_to_3min(df_1m):
    """1分足データを3分足に変換"""
    df_3m = df_1m.resample('3min').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    return df_3m

def calculate_indicators(df):
    """MACDとRSIを計算"""
    close = df['Close']
    # RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain/loss))
    # MACD
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
        stock = yf.Ticker(code)
        # 1分足を5日分取得
        df_1m = stock.history(period="5d", interval="1m")
        if df_1m.empty: return None

        # 3分足に変換
        df = resample_to_3min(df_1m)
        df = calculate_indicators(df)

        now = df.iloc[-1]
        prev = df.iloc[-2]

        signals = []

        # 1. 🔮 MACDクロス予兆 (ヒストグラム縮小 + RSI上昇)
        macd_improving = (now['Hist'] < 0) and (now['Hist'] > prev['Hist'])
        rsi_rising = (now['RSI'] > prev['RSI']) and (now['RSI'] < 60)
        
        if macd_improving and rsi_rising:
            # クロスが近いか判定（閾値は調整可）
            if now['Hist'] > -2.0: 
                signals.append(f"⚡ MACDクロス直前 (RSI:{now['RSI']:.1f})")

        # 2. 🕯️ 強いローソク足 (包み足)
        is_bullish_engulfing = (prev['Close'] < prev['Open']) and \
                               (now['Close'] > now['Open']) and \
                               (now['Open'] < prev['Close']) and \
                               (now['Close'] > prev['Open'])
        if is_bullish_engulfing:
            signals.append("🔥 陽の包み足 (強い買い)")

        # 3. ゴールデンクロス確定
        if (prev['Hist'] < 0) and (now['Hist'] > 0):
            signals.append("✅ MACDゴールデンクロス発生")

        if signals:
            return f"**{name} ({code.replace('.T','')})**\n" + "\n".join(signals) + f"\n現在値: {int(now['Close'])}円"
        return None

    except Exception as e:
        print(f"Error {code}: {e}")
        return None

def job():
    # シートから最新リストを取得
    watch_list = get_watch_list()
    
    messages = []
    for code, name in watch_list.items():
        msg = check_signals(code, name)
        if msg: messages.append(msg)
            
    if messages:
        full_msg = "🦅 **AI株価監視 (シート連動版)**\n" + "\n".join(messages)
        requests.post(DISCORD_WEBHOOK_URL, json={"content": full_msg})
        print("通知送信完了")
    else:
        print("シグナルなし")

# ==========================================
# 🚀 実行制御 (時間指定 09:00-11:10, 12:30-14:50)
# ==========================================
if __name__ == "__main__":
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)
    current_time = now.strftime("%H:%M")
    
    print(f"現在時刻(JST): {current_time}")

    # 監視時間帯の設定
    is_market_open = ("09:00" <= current_time <= "11:10") or \
                     ("12:30" <= current_time <= "14:50")

    if now.weekday() <= 4 and is_market_open:
        print("🔍 市場オープン中。スキャン開始...")
        job()
    else:
        print("💤 監視時間外です。")
