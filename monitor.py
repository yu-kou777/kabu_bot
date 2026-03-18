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
# ※エラーが出る場合は Google AI Studio で新しいキーを発行してください
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
MIN_VOLUME_5D = 100000 
PRICE_MIN = 500 
VOLATILITY_THRESHOLD = 0.04  # 直近5日の振幅が4%以上の「暴れ馬」を優先

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
        return {"8035.T": "東エレク(プ)", "9984.T": "SBG(プ)", "7203.T": "トヨタ(プ)", "8306.T": "三菱UFJ(プ)"}

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
        for i in range(0, len(text), 1900):
            requests.post(DISCORD_URL, json={"content": text[i:i+1900]}, timeout=10)
            time.sleep(1)
    except Exception as e:
        print(f"Discord送信エラー: {e}")

def get_ai_insight(msg_text):
    # プロンプトを極限まで圧縮。1銘柄に絞らせることでエラー率を下げる
    prompt = f"日本株プロとして以下から本命1銘柄を厳選し、注意点と目標値を150字以内で述べよ。データ:\n{msg_text}"
    
    # v1beta を使用し、より安定したエンドポイントを叩く
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.4}
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        # 403や429などのステータスコードをチェック
        if res.status_code != 200:
            return f"AIエラー: ステータス {res.status_code} (キー制限または設定ミス)"
            
        data = res.json()
        # 応答のパース処理を堅牢化
        if "candidates" in data and data["candidates"]:
            candidate = data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                return candidate["content"]["parts"][0]["text"]
        
        return "AI分析：適切な回答が得られませんでした。指標を優先してください。"
    except Exception as e:
        return f"AI通信エラー: {str(e)[:50]}"

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print("🚀 VWAP乖離＆ボラティリティ・スキャン開始...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    categories = {
        "🔴【空売り候補】": [], "🟢【反発狙い】": [], 
        "✨【同時GC】": [], "🚀【急騰期待】": []
    }
    
    chunk_size = 120 
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            # 高速化のため threads=True
            data = yf.download(chunk, period="1y", interval="1d", progress=False, threads=True)
            close_df = data['Close']
            vol_df = data['Volume']
            high_df = data['High']
            low_df = data['Low']
            
            rsi_s = get_rsi_vectorized(close_df, 9)
            rsi_l = get_rsi_vectorized(close_df, 14)
            rci_s = get_rci_vectorized(close_df, 9)
            rci_l = get_rci_vectorized(close_df, 26)
            
            # VWAP計算用
            cv_df = close_df * vol_df

            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    if len(c) < 200 or c.iloc[-1] < PRICE_MIN: continue
                    
                    v = vol_df[s].dropna()
                    if v.tail(5).mean() < MIN_VOLUME_5D: continue

                    # --- 値動き（ボラティリティ）の厳選 ---
                    # 直近5日の振幅をチェック
                    recent_vol = (high_df[s].tail(5).max() - low_df[s].tail(5).min()) / c.iloc[-1]
                    if recent_vol < VOLATILITY_THRESHOLD: continue

                    p = c.iloc[-1]
                    
                    # VWAP乖離率
                    v_sum_25 = vol_df[s].tail(25).sum()
                    vwap_25 = cv_df[s].tail(25).sum() / v_sum_25 if v_sum_25 > 0 else p
                    kairi = ((p - vwap_25) / vwap_25) * 100

                    c_rs, p_rs = rsi_s[s].iloc[-1], rsi_s[s].iloc[-2]
                    c_rl, p_rl = rsi_l[s].iloc[-1], rsi_l[s].iloc[-2]
                    c_rcs, p_rcs = rci_s[s].iloc[-1], rci_s[s].iloc[-2]
                    c_rcl = rci_l[s].iloc[-1]
                    
                    rsi_gc = (p_rs <= p_rl and c_rs > c_rl)
                    rci_gc = (p_rcs <= rci_l[s].iloc[-2] and c_rcs > c_rcl)
                    
                    # 情報を整形
                    info = f"・{name_map[s]} ({s})\n   価:{p:,.0f} 乖離:{kairi:+.1f}% RSI:{c_rs:.0f}/RCI:{c_rcs:.0f}"

                    # 判定条件
                    if c_rs >= 85 and c_rcs >= 90: categories["🔴【空売り候補】"].append((kairi, info))
                    elif c_rs <= 18 and c_rcs <= -75: categories["🟢【反発狙い】"].append((kairi, info))
                    elif rsi_gc and rci_gc and c_rs < 45: categories["✨【同時GC】"].append((kairi, info))
                    elif c_rs <= 10: categories["🚀【急騰期待】"].append((kairi, info))
                        
                except: continue
        except: continue
        time.sleep(1.2) # 負荷軽減

    ai_text = ""
    for cat, items in categories.items():
        if items:
            # 乖離の絶対値が大きい順（極端な値ほどチャンス）にソート
            top_items = sorted(items, key=lambda x: abs(x[0]), reverse=True)[:3]
            msg = f"**{cat}**\n" + "\n".join([x[1] for x in top_items])
            send_discord(msg)
            # AIへの負荷を減らすため、各カテゴリのトップ1件だけをAIに渡す
            ai_text += f"{cat}:{top_items[0][1]}\n"

    if ai_text:
        print("🤖 AI分析中...")
        insight = get_ai_insight(ai_text)
        send_discord(f"🤖 **【AI厳選・短評】**\n{insight}")
    else:
        send_discord("🔍 条件に合致する高ボラティリティ銘柄はありませんでした。")

    print("✅ 全処理完了")

if __name__ == "__main__":
    main()
