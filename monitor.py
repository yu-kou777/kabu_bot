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

# --- ⚙️ 継承設定 ---
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
MIN_VOLUME_5D = 300000 
PRICE_MIN = 3000 

def is_market_holiday():
    """日本市場の休日・祝日判定"""
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    # 土日(5,6) または 祝日
    if now.weekday() >= 5 or jpholiday.is_holiday(now.date()):
        return True
    return False

def calculate_vwap(df):
    """VWAP算出"""
    if df.empty: return 0
    try:
        c = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        v = df['Volume'].iloc[:,0] if isinstance(df['Volume'], pd.DataFrame) else df['Volume']
        return (c * v).sum() / v.sum()
    except: return 0

def get_prime_tickers():
    """JPXからプライム銘柄リスト取得"""
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム', na=False)]
        return {str(row['コード']) + ".T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        print(f"JPX Error: {e}")
        return {"8035.T": "東エレク", "9984.T": "SBG", "7203.T": "トヨタ", "6920.T": "レーザーテク"}

def calculate_rsi(df, period=14):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def calculate_rci(df, period=9):
    def rci_logic(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_logic)

def get_ai_insight(msg_text):
    """Gemini AIによる攻略本生成"""
    prompt = f"日本株プロとして分析。以下のデータから翌日のデイトレ準備ができる攻略本（注目点、上昇予想日、目標価格）を詳細に作成せよ。\n\n{msg_text}"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_KEY}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return "AI分析に失敗しました。"

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print("🚀 背景監視スキャンを開始...")
    name_map = get_prime_tickers()
    tickers = list(name_map.keys())
    
    hits = []
    # 200銘柄ずつのバッチ処理
    chunk_size = 200
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="6mo", interval="1d", progress=False)
            close_df = data['Close'] if 'Close' in data else data
            vol_df = data['Volume'] if 'Volume' in data else None
            
            rsi_s = calculate_rsi(close_df, 14)
            rci_s = calculate_rci(close_df, 9)
            ma5 = close_df.rolling(5).mean()
            ma25 = close_df.rolling(25).mean()

            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    if c.empty or c.iloc[-1] < PRICE_MIN: continue
                    if vol_df is not None and vol_df[s].tail(5).mean() < MIN_VOLUME_5D: continue

                    p, rsi, rci = c.iloc[-1], rsi_s[s].iloc[-1], rci_s[s].iloc[-1]
                    
                    # 💡 シグナル検知 (RCI底打ち・過熱、またはRSI)
                    if rci <= -80 or rci >= 85 or rsi <= 25 or rsi >= 75:
                        df_intra = yf.download(s, period="1d", interval="5m", progress=False)
                        vwap = calculate_vwap(df_intra)
                        dc = "あり" if (ma5[s].iloc[-1] < ma25[s].iloc[-1] and ma5[s].iloc[-2] >= ma25[s].iloc[-2]) else "なし"
                        hits.append(f"・{name_map[s]} ({s}): {p:,.1f}円 / VWAP:{vwap:.1f} / RSI:{rsi:.1f} / RCI:{rci:.1f} [DC:{dc}]")
                except: continue
        except: continue
        time.sleep(2)

    if hits:
        summary = f"📊 **【Jack株AI：スキャン速報】**\n" + "\n".join(hits[:15]) # 上位15件
        requests.post(DISCORD_URL, json={"content": summary[:1900]})
        
        ai_msg = get_ai_insight(summary)
        requests.post(DISCORD_URL, json={"content": f"🤖 **【AI翌日攻略本】**\n\n{ai_msg[:1900]}"})
    else:
        print("合致なし")

if __name__ == "__main__":
    main()
