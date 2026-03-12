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
MIN_VOLUME_MA5 = 300000 
PRICE_MIN = 3000 

def is_market_holiday():
    """日本市場の休日・祝日判定"""
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    if now.weekday() >= 5 or jpholiday.is_holiday(now.date()):
        return True
    return False

def calculate_vwap(df_intraday):
    """当日の5分足からVWAPを算出"""
    if df_intraday.empty: return 0
    try:
        c = df_intraday['Close'].iloc[:,0] if isinstance(df_intraday['Close'], pd.DataFrame) else df_intraday['Close']
        v = df_intraday['Volume'].iloc[:,0] if isinstance(df_intraday['Volume'], pd.DataFrame) else df_intraday['Volume']
        return (c * v).sum() / v.sum()
    except: return 0

def get_prime_tickers():
    """JPXからプライム銘柄を取得"""
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        res = requests.get(url, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム', na=False)]
        return {str(row['コード']) + ".T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except:
        return {"8035.T": "東エレク", "9984.T": "SBG", "7203.T": "トヨタ"}

def get_rsi(df, period=14):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def get_rci(df, period=9):
    def rci_func(x):
        n = len(x)
        t_rank = np.arange(1, n + 1)
        p_rank = pd.Series(x).rank().values
        return (1 - (6 * np.sum((t_rank - p_rank)**2)) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_func)

def get_ai_prediction(hits_data):
    """Gemini APIによる翌日攻略の予報"""
    prompt = f"日本株プロとして分析。条件を精査し、上昇予想日、目標価格、変動要因を詳細に解説せよ。\n\n{hits_data}"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, timeout=30)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return "AI分析エラー"

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print("🚀 背景スキャン開始...")
    name_map = get_prime_tickers()
    tickers = list(name_map.keys())
    
    all_hits = []
    chunk_size = 300
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        data = yf.download(chunk, period="6mo", interval="1d", progress=False)
        close_df = data['Close'] if 'Close' in data else data
        vol_df = data['Volume'] if 'Volume' in data else None
        
        rsi_s = get_rsi(close_df, 14)
        rci_s = get_rci(close_df, 9)
        ma5 = close_df.rolling(5).mean()
        ma25 = close_df.rolling(25).mean()

        for symbol in chunk:
            try:
                c = close_df[symbol].dropna()
                if c.empty or c.iloc[-1] < PRICE_MIN: continue
                if vol_df is not None and vol_df[symbol].tail(5).mean() < MIN_VOLUME_MA5: continue

                curr_p, rsi, rci = c.iloc[-1], rsi_s[symbol].iloc[-1], rci_s[symbol].iloc[-1]
                
                # シグナル判定
                if (rci <= -80 or rci >= 85 or rsi <= 25 or rsi >= 75):
                    # VWAP取得（当日の5分足）
                    df_intra = yf.download(symbol, period="1d", interval="5m", progress=False)
                    vwap = calculate_vwap(df_intra)
                    dc_info = "あり" if (ma5[symbol].iloc[-1] < ma25[symbol].iloc[-1] and ma5[symbol].iloc[-2] >= ma25[symbol].iloc[-2]) else "なし"
                    
                    all_hits.append(f"・{name_map[symbol]} ({symbol}): 価格{curr_p:,.1f}/VWAP{vwap:.1f}/RSI{rsi:.1f}/RCI{rci:.1f} [DC:{dc_info}]")
            except: continue
        time.sleep(2)

    if all_hits:
        msg = f"📊 **【Jack株AI：スキャン速報】**\n" + "\n".join(all_hits)
        requests.post(DISCORD_URL, json={"content": msg[:1900]})
        ai_msg = get_ai_prediction(msg)
        requests.post(DISCORD_URL, json={"content": f"🤖 **【AI攻略本】**\n\n{ai_msg[:1900]}"})

if __name__ == "__main__":
    main()
