import yfinance as yf
import pandas as pd
import requests
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime

# --- 設定 ---
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

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
    
    now_str = datetime.now().strftime('%m/%d %H:%M')
    data_msg = f"📊 **【Jack株AI テクニカル速報】** ({now_str})\n\n"
    summary_for_ai = ""
    
    # 1. データ収集と計算
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
            else:
                alert = "✅"
            
            line = f"{alert} {name}: RSI:{rsi} / RCI:{rci} ({price}円)\n"
            data_msg += line
            summary_for_ai += line
        except:
            pass

    # 2. 【第一陣】テクニカルデータだけを確実にDiscordへ送信
    try:
        for i in range(0, len(data_msg), 1900):
            DiscordWebhook(url=DISCORD_URL, content=data_msg[i:i+1900]).execute()
            time.sleep(1)
        print("✅ 第一陣：テクニカル速報の送信完了！")
    except Exception as e:
        print(f"❌ 速報の送信に失敗: {e}")

    # 3. 【第二陣】AIに裏方で攻略本を執筆させる
    print("🤖 AIが裏方で攻略本を執筆中...")
    prompt = f"日本株プロとして分析。特に🔥の底打ち銘柄を重視し、変動要因、上昇期待日、目標株価を銘柄ごとに3行で簡潔に分析せよ。\n\n{summary_for_ai}"
    
    try:
        # 404エラー対策：安定版の v1 エンドポイントを使用
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        headers = {'Content-Type': 'application/json'}
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            ai_analysis = response.json()['candidates'][0]['content']['parts'][0]['text']
            ai_msg = f"🤖 **【AI攻略本】**\n\n{ai_analysis}"
            
            # 成功した場合のみ追撃で送信
            for i in range(0, len(ai_msg), 1900):
                DiscordWebhook(url=DISCORD_URL, content=ai_msg[i:i+1900]).execute()
                time.sleep(1)
            print("✅ 第二陣：AI攻略本の送信完了！")
        else:
            # エラーの場合はDiscordに送らず、ログだけで黙って終了
            print(f"⚠️ AIは裏方で沈黙しました (エラーコード: {response.status_code})")
    except Exception as e:
        print(f"⚠️ AI通信エラーのため裏方で処理を終了します。")

if __name__ == "__main__":
    main()
