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
GEMINI_KEY = "AIzaSyBUiTPV-0yOXIDzgydV4NoArJkBufJSpys"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

# 厳格なフィルタ条件
PRICE_MIN = 1500
VOLATILITY_THRESHOLD = 0.035 
MIN_VOLUME_5D = 100000

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    return now.weekday() >= 5 or jpholiday.is_holiday(now.date())

def get_target_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        target_df = df[df['市場・商品区分'].str.contains('プライム|スタンダード', na=False)]
        return {str(row['コード']) + ".T": f"{row['銘柄名']}({row['市場・商品区分'][:1]})" for _, row in target_df.iterrows()}
    except:
        return {"7203.T": "トヨタ", "8306.T": "三菱UFJ", "9984.T": "SBG", "8035.T": "東エレク"}

def get_rsi_vectorized(df, period):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss + 1e-9)))

def get_rci_vectorized(df, period):
    def _rci(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(_rci)

def send_discord(text, title=None, is_ai=False):
    if not text.strip(): return
    
    # AIの回答か、銘柄リストかで装飾を変える
    if is_ai:
        content = f"### 🤖 AIプロの売買助言\n> {text}"
    else:
        # 見やすい大見出しと区切り線
        content = f"# {title}\n{text}"
        
    try:
        # 2000文字を超える場合は分割送信
        for i in range(0, len(content), 1950):
            requests.post(DISCORD_URL, json={"content": content[i:i+1950]}, timeout=10)
            time.sleep(1)
    except Exception as e:
        print(f"Discordエラー: {e}")

def get_ai_insight(msg_text):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = f"日本株プロとして以下の銘柄リストから1つ厳選し、買い時/売り時を100字以内で述べよ:\n{msg_text}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=12)
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        return None
    except:
        return None

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print(f"🚀 スキャン開始...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    categories = {
        "🟢【底打ち期待】RCI/RSI 低位": [],
        "🔴【過熱警戒】RCI/RSI 高位": [],
        "✨【RCIゴールデンクロス】": [],
        "💀【RCIデッドクロス】": []
    }
    
    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False, threads=True)
            close_df, vol_df, high_df, low_df = data['Close'], data['Volume'], data['High'], data['Low']
            
            rsi_df = get_rsi_vectorized(close_df, 14)
            rci9_df = get_rci_vectorized(close_df, 9)
            rci26_df = get_rci_vectorized(close_df, 26)
            cv_df = close_df * vol_df

            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    if len(c) < 30 or c.iloc[-1] < PRICE_MIN: continue
                    v = vol_df[s].dropna()
                    if v.tail(5).mean() < MIN_VOLUME_5D: continue

                    p = c.iloc[-1]
                    v_sum = v.tail(25).sum()
                    vwap25 = cv_df[s].tail(25).sum() / v_sum if v_sum > 0 else p
                    kairi = ((p - vwap25) / vwap25) * 100
                    
                    r9_curr, r9_prev = rci9_df[s].iloc[-1], rci9_df[s].iloc[-2]
                    r26_curr, r26_prev = rci26_df[s].iloc[-1], rci26_df[s].iloc[-2]
                    rsi_curr = rsi_df[s].iloc[-1]
                    
                    vol_val = (high_df[s].tail(5).max() - low_df[s].tail(5).min()) / p
                    if vol_val < VOLATILITY_THRESHOLD: continue

                    # --- 表示用フォーマット作成 ---
                    # 1銘柄を1つのブロックとして構成
                    stock_card = (
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"**{s.replace('.T','')} : {name_map[s]}**\n"
                        f"┣ 株価: `{p:,.0f}円` (乖離: `{kairi:+.1f}%`)\n"
                        f"┗ RCI9: `{r9_curr:.0f}` / RSI: `{rsi_curr:.0f}`\n"
                    )

                    # 分類
                    if r9_curr <= -30 and rsi_curr <= 30:
                        categories["🟢【底打ち期待】RCI/RSI 低位"].append((kairi, stock_card))
                    elif r9_curr >= 80 and rsi_curr >= 80:
                        categories["🔴【過熱警戒】RCI/RSI 高位"].append((kairi, stock_card))
                    
                    if r9_prev <= r26_prev and r9_curr > r26_curr and r9_curr < 0:
                        categories["✨【RCIゴールデンクロス】"].append((kairi, stock_card))
                    elif r9_prev >= r26_prev and r9_curr < r26_curr and r9_curr > 0:
                        categories["💀【RCIデッドクロス】"].append((kairi, stock_card))

                except: continue
        except: continue
        time.sleep(1)

    ai_input = ""
    hit_any = False

    for cat_name, items in categories.items():
        if items:
            hit_any = True
            # 乖離率の順でソートして上位5件を表示
            sorted_items = sorted(items, key=lambda x: abs(x[0]), reverse=True)[:5]
            display_text = "".join([x[1] for x in sorted_items]) + "━━━━━━━━━━━━━━━━━━"
            send_discord(display_text, title=cat_name)
            ai_input += f"【{cat_name}】\n" + sorted_items[0][1]

    if hit_any:
        print("🤖 AI分析中...")
        ai_msg = get_ai_insight(ai_input)
        if ai_msg:
            send_discord(ai_msg, is_ai=True)
    else:
        send_discord("本日の厳格条件に合致する銘柄はありません。", title="🔍 スキャン完了")

    print("✅ 全工程完了")

if __name__ == "__main__":
    main()
