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
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
MIN_VOLUME_5D = 100000 
PRICE_MIN = 500 
VOLATILITY_THRESHOLD = 0.03  # 直近5日の振幅が3%以上の銘柄を優先

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

def send_discord(text):
    if not text.strip(): return
    try:
        # Discordの文字数制限2000文字対策
        for i in range(0, len(text), 1900):
            requests.post(DISCORD_URL, json={"content": text[i:i+1900]}, timeout=10)
            time.sleep(1)
    except Exception as e:
        print(f"Discordエラー: {e}")

def get_ai_insight(msg_text):
    # プロンプトを極限まで短縮し、エラーを回避
    prompt = f"日本株プロとして以下を300字以内で短評せよ。1.本命1銘柄 2.だまし回避の注意点 3.目標株価。データ：\n{msg_text}"
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 400, "temperature": 0.7}
        }
        res = requests.post(url, json=payload, timeout=30)
        data = res.json()
        return data['candidates'][0]['content']['parts'][0]['text']
    except:
        return "AI分析：現在データが混み合っています。各指標を確認してください。"

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print("🚀 スキャン開始（ボラティリティ重視モード）...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    categories = {
        "🔴【空売り候補】": [], "🟢【反発狙い】": [], 
        "✨【同時GC】": [], "🚀【急騰期待】": []
    }
    
    chunk_size = 100 # サイトに蹴られない適正サイズ
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            # threads=Trueで高速化
            data = yf.download(chunk, period="1y", interval="1d", progress=False, threads=True)
            close_df = data['Close']
            vol_df = data['Volume']
            high_df = data['High']
            low_df = data['Low']
            
            rsi_s = get_rsi_vectorized(close_df, 9)
            rsi_l = get_rsi_vectorized(close_df, 14)
            rci_s = get_rci_vectorized(close_df, 9)
            rci_l = get_rci_vectorized(close_df, 26)
            
            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    if len(c) < 200 or c.iloc[-1] < PRICE_MIN: continue
                    
                    v = vol_df[s].dropna()
                    if v.tail(5).mean() < MIN_VOLUME_5D: continue

                    # --- 値動き（ボラティリティ）判定 ---
                    # 直近5日の(高値-安値)/株価 で振幅を計算
                    recent_volatility = (high_df[s].tail(5).max() - low_df[s].tail(5).min()) / c.iloc[-1]
                    if recent_volatility < VOLATILITY_THRESHOLD: continue

                    p = c.iloc[-1]
                    ma25 = c.rolling(25).mean().iloc[-1]
                    vwap_25d = (close_df[s].tail(25) * vol_df[s].tail(25)).sum() / vol_df[s].tail(25).sum()
                    kairi = ((p - vwap_25d) / vwap_25d) * 100

                    c_rs, p_rs = rsi_s[s].iloc[-1], rsi_s[s].iloc[-2]
                    c_rl, p_rl = rsi_l[s].iloc[-1], rsi_l[s].iloc[-2]
                    c_rcs, p_rcs = rci_s[s].iloc[-1], rci_s[s].iloc[-2]
                    c_rcl = rci_l[s].iloc[-1]
                    
                    rsi_gc = (p_rs <= p_rl and c_rs > c_rl)
                    rci_gc = (p_rcs <= rci_l[s].iloc[-2] and c_rcs > c_rcl)
                    
                    info = f"・{name_map[s]} ({s})\n   価:{p:,.0f} 乖離:{kairi:+.1f}% RSI:{c_rs:.0f}"

                    if c_rs >= 85 and c_rcs >= 90: categories["🔴【空売り候補】"].append((kairi, info))
                    elif c_rs <= 20 and c_rcs <= -75: categories["🟢【反発狙い】"].append((kairi, info))
                    elif rsi_gc and rci_gc and c_rs < 50: categories["✨【同時GC】"].append((kairi, info))
                    elif c_rs <= 12: categories["🚀【急騰期待】"].append((kairi, info))
                        
                except: continue
        except: continue
        time.sleep(1.5) # 負荷軽減のウェイト

    ai_text = ""
    for cat, items in categories.items():
        if items:
            # 乖離率でソートして上位3件を表示
            top_items = sorted(items, key=lambda x: abs(x[0]), reverse=True)[:3]
            msg = f"**{cat}**\n" + "\n".join([x[1] for x in top_items])
            send_discord(msg)
            # AIには各カテゴリのトップ1件だけを渡して短縮
            ai_text += f"{cat}:{top_items[0][1]}\n"

    if ai_text:
        print("🤖 AI分析中...")
        insight = get_ai_insight(ai_text)
        send_discord(f"🤖 **【AI厳選・短評】**\n{insight}")

    print("✅ 完了")

if __name__ == "__main__":
    main()
