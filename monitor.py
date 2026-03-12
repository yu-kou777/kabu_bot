import yfinance as yf
import pandas as pd
import requests
import time
import numpy as np
import json
import io
from datetime import datetime
import pytz
import jpholiday

# --- 設定 ---
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
MIN_VOLUME_5D = 300000 
PRICE_MIN = 3000 

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    if now.weekday() >= 5 or jpholiday.is_holiday(now.date()):
        return True
    return False

def get_prime_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム', na=False)]
        return {str(row['コード']) + ".T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except:
        return {
            "8035.T": "東エレク", "9984.T": "SBG", "7203.T": "トヨタ", "6920.T": "レーザーテク",
            "6857.T": "アドバンテ", "6146.T": "ディスコ", "6723.T": "ルネサス", "7974.T": "任天堂",
            "4063.T": "信越化", "8306.T": "三菱UFJ", "9101.T": "日本郵船", "9020.T": "JR東日本"
        }

def calculate_rsi(df, period=14):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss + 1e-9)))

def calculate_rci(df, period=9):
    def rci_logic(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_logic)

def get_ai_insight(msg_text):
    prompt = f"日本株のプロとして以下の検知された銘柄データを分析してください。翌日のデイトレ・スイングに向けた攻略本（各銘柄の連動要因、トレンド状況、上昇予想日、目標価格）を詳細に作成してください。\n\n{msg_text}"
    # 💡 友幸さんのキーで確実に動く安定版(1.5-flash)に変更しました
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    try:
        res = requests.post(url, headers=headers, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"AIエラー: {res.status_code}"
    except Exception as e: 
        return f"AI通信エラー: {e}"

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。処理を終了します。")
        return

    print("🚀 スキャン開始...")
    name_map = get_prime_tickers()
    tickers = list(name_map.keys())
    
    hits = []
    chunk_size = 100 
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="6mo", interval="1d", progress=False, threads=False)
            close_df = data['Close'] if 'Close' in data else data
            
            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    if c.empty or c.iloc[-1] < PRICE_MIN: continue
                    
                    p, rsi, rci = c.iloc[-1], calculate_rsi(c).iloc[-1], calculate_rci(c).iloc[-1]
                    
                    if rci <= -80 or rci >= 85 or rsi <= 25 or rsi >= 75:
                        hits.append(f"・{name_map[s]} ({s}): {p:,.1f}円 / RSI:{rsi:.1f} / RCI:{rci:.1f}")
                except: continue
        except: continue
        time.sleep(1)

    if hits:
        # ディスコードの文字数制限に引っかからないように調整
        summary = f"📊 **【Jack株AI：スキャン速報】**\n" + "\n".join(hits[:15])
        requests.post(DISCORD_URL, json={"content": summary[:1900]})
        
        # AI分析を実行
        ai_msg = get_ai_insight(summary)
        requests.post(DISCORD_URL, json={"content": f"🤖 **【AI攻略予報】**\n\n{ai_msg[:1900]}"})
    else:
        print("条件合致なし")

if __name__ == "__main__":
    main()
