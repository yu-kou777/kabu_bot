import yfinance as yf
import pandas as pd
import google.generativeai as genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os

# --- 設定（合鍵を直接セット） ---
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

# AIの初期化
genai.configure(api_key=GEMINI_KEY)

# 監視対象：主力24銘柄
TICKERS = {
    "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6758.T": "ソニーG",
    "7203.T": "トヨタ自動車", "6920.T": "レーザーテック", "6857.T": "アドバンテスト",
    "6146.T": "ディスコ", "4063.T": "信越化学", "8058.T": "三菱商事",
    "8316.T": "三井住友FG", "9101.T": "日本郵船", "7011.T": "三菱重工",
    "4502.T": "武田薬品", "6501.T": "日立製作所", "6702.T": "富士通",
    "6201.T": "豊田自動織機", "9104.T": "商船三井", "6367.T": "ダイキン工業",
    "6273.T": "SMC", "7974.T": "任天堂", "9020.T": "JR東日本",
    "2914.T": "JT", "4061.T": "デンカ", "6723.T": "ルネサス"
}

# --- テクニカル計算ロジック ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_rci(series, period=9):
    """
    RCI計算式:
    $$RCI = \left( 1 - \frac{6 \sum d^2}{n(n^2 - 1)} \right) \times 100$$
    """
    if len(series) < period: return np.zeros(len(series))
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

# --- メイン実行エンジン ---
def main():
    print("🚀 ジャック株AI：戦闘開始...")
    summary_text = ""
    
    for symbol, name in TICKERS.items():
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty: continue
            
            rsi = round(calculate_rsi(df['Close'], 14).iloc[-1], 1)
            rci = round(calculate_rci(df['Close'], 9)[-1], 1)
            price = f"{df['Close'].iloc[-1]:,.0f}"
            
            # ジャックさん専用・超絶判定
            alert = ""
            if rsi < 21 and rci < -79:
                alert = "🔥【超絶売られすぎ】"
            elif rsi > 89 and rci > 94:
                alert = "⚠️【超過熱・警戒】"
            
            summary_text += f"{alert}{name}({symbol}): RSI:{rsi}, RCI:{rci}, 価格:{price}円\n"
            print(f"✅ {name}: RSI:{rsi} / RCI:{rci} {alert}")
        except Exception as e:
            print(f"❌ {symbol} エラー: {e}")

    print("🤖 AIが攻略本を執筆中...")
    # 安定版の呼び出し方式に変更
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"日本株プロとして分析。特に🔥の底打ち銘柄を重視し、変動要因、上昇期待日、目標株価を銘柄ごとに3行で回答せよ。\n\n{summary_text}"
    
    try:
        response = model.generate_content(prompt)
        ai_analysis = response.text
    except Exception as e:
        ai_analysis = f"AI分析失敗: {str(e)}"

    # Discord報告
    now = datetime.now().strftime('%m/%d %H:%M')
    msg = f"📢 **【Jack株AI 定刻報告】** ({now})\n\n{ai_analysis}"
    
    # 分割送信
    for i in range(0, len(msg), 1900):
        DiscordWebhook(url=DISCORD_URL, content=msg[i:i+1900]).execute()
    
    print("✅ 全工程完了。Discordを確認してください。")

if __name__ == "__main__":
    main()
