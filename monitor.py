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
MIN_VOLUME_5D = 100000 # 💡 スタンダードにも対応できるよう10万株に緩和
PRICE_MIN = 500 # 💡 幅広いお宝を探すため500円以上に緩和

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    if now.weekday() >= 5 or jpholiday.is_holiday(now.date()):
        return True
    return False

def get_target_tickers():
    """JPXからプライム・スタンダード市場の銘柄を両方取得"""
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        # 💡 プライム と スタンダード 両方を抽出
        target_df = df[df['市場・商品区分'].str.contains('プライム|スタンダード', na=False)]
        
        # 銘柄名の後ろに (プ) または (ス) を付ける
        return {str(row['コード']) + ".T": f"{row['銘柄名']}({row['市場・商品区分'][:1]})" for _, row in target_df.iterrows()}
    except Exception as e:
        print(f"銘柄取得エラー: {e}")
        return {"8035.T": "東エレク(プ)", "9984.T": "SBG(プ)", "7203.T": "トヨタ(プ)"}

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

def get_trend_status(p, ma25, ma75):
    """だまし回避のためのトレンド判定（パーフェクトオーダーなど）"""
    if p > ma25 and ma25 > ma75:
        return "🚀強い上昇トレンド"
    elif p < ma25 and ma25 < ma75:
        return "📉強い下降トレンド"
    elif ma25 > ma75:
        return "↗️緩やかな上昇"
    else:
        return "↘️緩やかな下降"

def get_ai_insight(msg_text):
    prompt = f"""あなたは日本株のプロトレーダーです。以下のプライムおよびスタンダード市場から抽出された極端なシグナル（大底・ピークなど）が出ている銘柄群を分析してください。
    
    【必須項目】
    1. トレンド状況（強い上昇/下降）を考慮し、このシグナルが「だまし（Fake-out）」か「本物のチャンス」かを見極めること。
    2. その銘柄の連動要因（金利、為替、セクター動向など）。
    3. デイトレ・スイングでの具体的な買い時・売り時、上昇/反転の予想日、目標価格。
    
    【対象データ】
    {msg_text}
    """
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    try:
        res = requests.post(url, headers=headers, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        return f"AIエラー: {res.status_code}"
    except Exception as e: 
        return f"AI通信エラー: {e}"

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print("🚀 プライム・スタンダード 全域スキャン開始...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    hits = []
    chunk_size = 150 
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="6mo", interval="1d", progress=False, threads=False)
            close_df = data['Close'] if 'Close' in data else data
            vol_df = data['Volume'] if 'Volume' in data else None
            
            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    # 💡 上場直後や価格が安すぎる銘柄を除外
                    if len(c) < 75 or c.iloc[-1] < PRICE_MIN: continue
                    
                    # 💡 流動性のない「売れない株」を除外 (直近5日の平均出来高)
                    if vol_df is not None:
                        v = vol_df[s].dropna()
                        if len(v) < 5 or v.tail(5).mean() < MIN_VOLUME_5D: continue
                    
                    p = c.iloc[-1]
                    rsi = calculate_rsi(c).iloc[-1]
                    rci = calculate_rci(c).iloc[-1]
                    ma25 = c.rolling(25).mean().iloc[-1]
                    ma75 = c.rolling(75).mean().iloc[-1]
                    
                    # トレンド判定
                    trend = get_trend_status(p, ma25, ma75)
                    
                    # 視覚的シグナル判定
                    signal = ""
                    if rci <= -90 and rsi <= 30:
                        signal = "🔥大底(反転間近)"
                    elif rci <= -80 or rsi <= 25:
                        signal = "🔵買い時(底値圏)"
                    elif rci >= 90 and rsi >= 70:
                        signal = "🚨ピーク(下落間近)"
                    elif rci >= 80 or rsi >= 75:
                        signal = "🟠売り時(高値圏)"
                    
                    if signal:
                        hits.append(f"【{signal}】 {name_map[s]} ({s})\n  ⇒ 価格:{p:,.0f}円 | RSI:{rsi:.0f}/RCI:{rci:.0f} | トレンド:{trend}")
                except: continue
        except: continue
        time.sleep(1)

    if hits:
        # ディスコードに送信 (上位25件に絞る)
        summary = f"📊 **【Jack株AI：全市場 シグナル速報】**\n" + "\n".join(hits[:25])
        requests.post(DISCORD_URL, json={"content": summary[:1900]})
        
        # AI分析を実行
        ai_msg = get_ai_insight(summary)
        requests.post(DISCORD_URL, json={"content": f"🤖 **【AI だまし回避 ＆ 攻略予報】**\n\n{ai_msg[:1900]}"})
    else:
        print("条件合致なし")

if __name__ == "__main__":
    main()
