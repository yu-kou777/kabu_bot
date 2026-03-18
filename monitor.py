import yfinance as yf
import pandas as pd
import requests
import time
import numpy as np
import io
from datetime import datetime
import pytz
import jpholiday

# --- 設定 ---
# 【重要】もう一つのAPIキーをここに入れて試してください
GEMINI_KEY = "AIzaSyD0AyTtuRvEwv36ZtleptL6wbtolUMuIkk"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
MIN_VOLUME_5D = 100000 
PRICE_MIN = 500 
VOLATILITY_THRESHOLD = 0.035 

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    if now.weekday() >= 5 or jpholiday.is_holiday(now.date()):
        return True
    return False

def get_target_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        target_df = df[df['市場・商品区分'].str.contains('プライム|スタンダード', na=False)]
        return {str(row['コード']) + ".T": f"{row['銘柄名']}({row['市場・商品区分'][:1]})" for _, row in target_df.iterrows()}
    except:
        return {"8035.T": "東エレク(プ)", "9984.T": "SBG(プ)", "7203.T": "トヨタ(プ)"}

def get_rsi_vectorized(df, period):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss + 1e-9)))

def get_rci_vectorized(df, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_func)

def send_discord(text, title=None):
    if not text.strip(): return
    content = f"**【{title}】**\n{text}" if title else text
    try:
        requests.post(DISCORD_URL, json={"content": content}, timeout=10)
        time.sleep(1.2)
    except Exception as e:
        print(f"Discord送信エラー: {e}")

def get_ai_insight(msg_text):
    # 404対策：v1betaエンドポイントを使い、モデル名を正確に指定
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    prompt = f"株プロとして以下から本命1銘柄を厳選、理由と目標値を100字以内で。:\n{msg_text}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.4}
    }

    try:
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=15)
        if res.status_code == 200:
            data = res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        else:
            return f"AI分析停止 (Status: {res.status_code})\n詳細: {res.text[:50]}"
    except:
        return "AI分析スキップ (通信エラー)"

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print("🚀 スキャン開始（新APIキー適用版）...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    categories = {
        "🔴【空売り候補】": [], "🟢【反発狙い】": [], 
        "✨【同時GC】": [], "🚀【急騰期待】": []
    }
    
    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False, threads=True)
            close_df, vol_df, high_df, low_df = data['Close'], data['Volume'], data['High'], data['Low']
            
            rsi_s = get_rsi_vectorized(close_df, 9)
            rci_s = get_rci_vectorized(close_df, 9)
            rci_l = get_rci_vectorized(close_df, 26)
            cv_df = close_df * vol_df

            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    if len(c) < 200 or c.iloc[-1] < PRICE_MIN: continue
                    if vol_df[s].tail(5).mean() < MIN_VOLUME_5D: continue

                    # 値動き（ボラティリティ）で厳選
                    vol = (high_df[s].tail(5).max() - low_df[s].tail(5).min()) / c.iloc[-1]
                    if vol < VOLATILITY_THRESHOLD: continue

                    p = c.iloc[-1]
                    v_sum = vol_df[s].tail(25).sum()
                    vwap = cv_df[s].tail(25).sum() / v_sum if v_sum > 0 else p
                    kairi = ((p - vwap) / vwap) * 100
                    cur_rsi, cur_rci = rsi_s[s].iloc[-1], rci_s[s].iloc[-1]
                    
                    info = f"・{name_map[s]} ({s}) 価:{p:,.0f} 乖:{kairi:+.1f}% RSI:{cur_rsi:.0f}"

                    if cur_rsi >= 85 and cur_rci >= 90: categories["🔴【空売り候補】"].append((kairi, info))
                    elif cur_rsi <= 18 and cur_rci <= -75: categories["🟢【反発狙い】"].append((kairi, info))
                    elif cur_rsi < 45 and cur_rci > rci_l[s].iloc[-1] and rci_s[s].iloc[-2] <= rci_l[s].iloc[-2]:
                        categories["✨【同時GC】"].append((kairi, info))
                    elif cur_rsi <= 10: categories["🚀【急騰期待】"].append((kairi, info))
                except: continue
        except: continue
        time.sleep(1)

    ai_input_data = ""
    hit_flag = False
    
    # 銘柄リストを送信（AIの前に実行）
    for cat_name, items in categories.items():
        if items:
            hit_flag = True
            sorted_items = sorted(items, key=lambda x: abs(x[0]), reverse=True)[:5]
            display_text = "\n".join([x[1] for x in sorted_items])
            send_discord(display_text, title=f"📊 {cat_name} スキャン結果")
            ai_input_data += f"{cat_name}: {sorted_items[0][1]}\n"

    # AI短評を送信
    if hit_flag:
        print("🤖 AI分析中...")
        ai_comment = get_ai_insight(ai_input_data)
        send_discord(ai_comment, title="🤖 AIプロの厳選短評")
    else:
        send_discord("該当なし", title="🔍 スキャン完了")

    print("✅ 完了")

if __name__ == "__main__":
    main()
