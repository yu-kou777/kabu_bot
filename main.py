import yfinance as yf
import pandas as pd
import requests
import json
from datetime import datetime, timedelta, timezone
import os

# ==========================================
# ⚙️ 設定エリア
# ==========================================

# DiscordのURL (GitHubのSecretsに登録推奨ですが、まずはここに直書きでも動きます)
DISCORD_WEBHOOK_URL = "ここにあなたのDiscordウェブフックURLを貼り付けてください"

# 監視対象の銘柄コードと名前
WATCH_LIST = {
    "6098.T": "リクルート",
    "6758.T": "ソニーG",
    "9984.T": "SBG",
    "7203.T": "トヨタ",
    # 好きな銘柄を追加してください
}

# ==========================================
# 🧠 ロジックエリア
# ==========================================

def send_discord(message):
    """Discordにメッセージを送信する"""
    if not DISCORD_WEBHOOK_URL.startswith("http"):
        print("⚠️ Discord URLが設定されていません")
        return

    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
    except Exception as e:
        print(f"送信エラー: {e}")

def check_stock(ticker, name):
    """株価をチェックして条件に合えば通知用メッセージを返す"""
    try:
        stock = yf.Ticker(ticker)
        # 直近1日分のデータを取得
        hist = stock.history(period="1d")
        
        if hist.empty:
            return None

        # 現在値の取得
        current_price = hist["Close"].iloc[-1]
        
        # --- ここに通知したい条件を書く ---
        # 例: RSIなどを計算してもOKですが、まずはシンプルに価格表示
        return f"📈 **{name} ({ticker.replace('.T', '')})**\n現在値: {int(current_price)}円"

    except Exception as e:
        print(f"エラー ({name}): {e}")
        return None

def job():
    """全銘柄をチェックして通知"""
    messages = []
    
    for code, name in WATCH_LIST.items():
        msg = check_stock(code, name)
        if msg:
            messages.append(msg)
            
    # メッセージがあればまとめて送信
    if messages:
        full_msg = "🤖 **定期株価チェック**\n" + "\n".join(messages)
        send_discord(full_msg)
        print("✅ 通知送信完了")
    else:
        print("市場データなし、または条件該当なし")

# ==========================================
# 🚀 実行エントリーポイント
# ==========================================
if __name__ == "__main__":
    # 日本時間を設定
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)
    current_time = now.strftime("%H:%M")
    
    print(f"🤖 システム起動: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    # 平日の 09:00 〜 15:30 だけ動くように制限
    # (GitHub Actionsは土日も動いてしまうため、ここで弾く)
    weekday = now.weekday() # 0:月曜 〜 4:金曜
    
    if weekday <= 4 and "09:00" <= current_time <= "15:30":
        print("🔍 市場オープン中。スキャンを開始します...")
        job()
    else:
        print(f"💤 営業時間外です (現在: {current_time}, 曜日: {weekday})。終了します。")
