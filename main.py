import yfinance as yf
import pandas as pd
import google.generativeai as genai
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import os

# --- 設定（合鍵と住所） ---
# 💡 URLの最初から最後まで、余計な空白がないか確認してください！
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

genai.configure(api_key=GEMINI_KEY)

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

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_rci(series, period=9):
    if len(series) < period: return np.zeros(len(series))
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

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
            
            alert = ""
            if rsi < 21 and rci < -79:
                alert = "🔥【超絶売られすぎ】"
            elif rsi > 89 and rci > 94:
                alert = "⚠️【超過熱・警戒】"
            
            summary_text += f"{alert}{name}({symbol}): RSI:{rsi}, RCI:{rci}, 価格:{price}円\n"
        except Exception as e:
            pass

    print("🤖 AIが攻略本を執筆中...")
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"日本株プロとして分析。特に🔥の底打ち銘柄を重視し、変動要因、上昇期待日、目標株価を銘柄ごとに3行で簡潔に分析せよ。\n\n{summary_text}"
    
    try:
        response = model.generate_content(prompt)
        ai_analysis = response.text
        print("✅ AIの執筆が完了しました。Discordへ送信を開始します。")
    except Exception as e:
        ai_analysis = f"AI分析失敗: {str(e)}"
        print("❌ AIの執筆でエラーが発生しました。")

    # Discord報告（確実な分割送信とエラーチェック）
    now_str = datetime.now().strftime('%m/%d %H:%M')
    msg = f"📢 **【Jack株AI 定刻報告】** ({now_str})\n\n{ai_analysis}"
    
    chunk_size = 1800 # 余裕を持たせて1800文字ずつ送信
    chunks = [msg[i:i+chunk_size] for i in range(0, len(msg), chunk_size)]
    
    success_count = 0
    for i, chunk in enumerate(chunks):
        try:
            webhook = DiscordWebhook(url=DISCORD_URL, content=chunk)
            response = webhook.execute()
            # HTTPステータスコードが200番台なら成功
            if response.status_code >= 200 and response.status_code < 300:
                success_count += 1
            else:
                print(f"❌ Discord送信エラー (Chunk {i+1}): ステータスコード {response.status_code}")
        except Exception as e:
            print(f"❌ Discord送信致命的エラー: {e}")
        time.sleep(1) # 連続送信によるスパム判定を回避
    
    if success_count == len(chunks):
        print(f"✅ 全{len(chunks)}通のメッセージがDiscordへ正常に送信されました！")
    else:
        print(f"⚠️ 一部のメッセージが送信できませんでした ({success_count}/{len(chunks)} 成功)")

if __name__ == "__main__":
    main()
