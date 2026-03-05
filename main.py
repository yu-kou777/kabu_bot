import yfinance as yf
import pandas as pd
import pandas_ta as ta
import google.generativeai as genai
from discord_webhook import DiscordWebhook
import time

# --- ジャックさんの設定 ---
GENAI_API_KEY = "gen-lang-client-0447054408"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 監視対象（ここを100銘柄まで増やせます）
TICKERS = [
    "8035.T", "9984.T", "6758.T", "7203.T", "6920.T", "6857.T", "6146.T", "4063.T",
    "8058.T", "8316.T", "9101.T", "7011.T", "4502.T", "6501.T", "6702.T", "6201.T",
    "9104.T", "6367.T", "6273.T", "7974.T", "9020.T", "2914.T", "4061.T", "6723.T"
]

def run_scan():
    print(f"🚀 スキャン開始: {len(TICKERS)}銘柄")
    
    for i, symbol in enumerate(TICKERS):
        try:
            # 1. データ取得
            stock = yf.Ticker(symbol)
            df = stock.history(period="3mo")
            if df.empty: continue

            # 2. テクニカル計算
            df['RSI'] = ta.rsi(df['Close'], length=14)
            df['RCI'] = ta.rci(df['Close'], length=9)
            
            last = df.iloc[-1]
            
            # 3. API制限回避のウェイト（5銘柄ごとに長めの休憩）
            if i % 5 == 0 and i > 0:
                print("⏳ APIリミット回避中...")
                time.sleep(10)

            # 4. AI分析
            prompt = f"""
            銘柄:{symbol} / 価格:{last['Close']:.0f}円 / RSI:{last['RSI']:.1f} / RCI:{last['RCI']:.1f}
            上記データから、明日の戦略、上昇期待日、目標株価を3行で回答して。
            """
            response = model.generate_content(prompt)
            
            # 5. Discord送信
            msg = f"💎 **{symbol}**\n現値: {last['Close']:,.0f}円\n{response.text}"
            DiscordWebhook(url=DISCORD_WEBHOOK_URL, content=msg).execute()
            
            print(f"✅ {symbol} 完了")
            time.sleep(1) 

        except Exception as e:
            print(f"❌ {symbol} エラー: {e}")

if __name__ == "__main__":
    run_scan()
