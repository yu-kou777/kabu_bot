import yfinance as yf
import pandas as pd
import requests
import time
import numpy as np
import io
from datetime import datetime
import pytz
import jpholiday

# --- ⚙️ 設定 ---
GEMINI_KEY = "AIzaSyBUiTPV-0yOXIDzgydV4NoArJkBufJSpys"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

MIN_VOLUME_5D = 300000 
PRICE_MIN = 300 

# --- 📊 指標計算ユニット ---
def calculate_rsi(df, period=14):
    delta = df.diff(); gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / (loss + 1e-9))))

def calculate_rci(df, period):
    def _rci(x):
        n = len(x); d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(_rci)

def calculate_psychological(df, period=12):
    return ((df.diff() > 0).astype(int).rolling(window=period).sum() / period) * 100

def calculate_vwap(data, period=25):
    tp = (data['High'] + data['Low'] + data['Close']) / 3
    return (tp * data['Volume']).rolling(window=period).sum() / (data['Volume'].rolling(window=period).sum() + 1e-9)

def get_sakata_signal(h, l, o, c, v):
    """酒田五法フィルター：強力な反転・継続サインのみを抽出"""
    s = []
    # 1. 赤三兵（強気継続・反転初動）
    if (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-2] > o.iloc[-2]) and (c.iloc[-3] > o.iloc[-3]) and (c.iloc[-1] > c.iloc[-2] > c.iloc[-3]):
        s.append("🔆赤三兵(強気)")
    # 2. 包み足（大反転）
    if (c.iloc[-2] < o.iloc[-2]) and (c.iloc[-1] > o.iloc[-1]) and (o.iloc[-1] <= c.iloc[-2]) and (c.iloc[-1] >= o.iloc[-2]):
        s.append("🔥陽の包み足(反転)")
    # 3. 窓開け（勢い加速）
    if l.iloc[-1] > h.iloc[-2]:
        s.append("✨上放れ窓(加速)")
    # 4. 明けの明星（底打ち）
    if (c.iloc[-3] < o.iloc[-3]) and (abs(c.iloc[-2] - o.iloc[-2]) < abs(c.iloc[-3] - o.iloc[-3]) * 0.2) and (c.iloc[-1] > o.iloc[-1]):
        s.append("🌅明けの明星(底)")
    return " ".join(s)

def send_discord(text, title=None, color=0x2ecc71):
    if not text.strip(): return
    payload = {"embeds": [{"title": title, "description": text, "color": color, "timestamp": datetime.now().isoformat()}]}
    try:
        requests.post(DISCORD_URL, json=payload, timeout=10)
        time.sleep(1)
    except: pass

def get_target_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        target_df = df[df['市場・商品区分'].str.contains('プライム|スタンダード', na=False)]
        return {str(row['コード']) + ".T": f"{row['銘柄名']}" for _, row in target_df.iterrows()}
    except: return {"8035.T": "東エレク", "9984.T": "SBG"}

def main():
    name_map = get_target_tickers(); tickers = list(name_map.keys())
    categories = {
        "🏹【酒田×RCI 究極スナイプ】": {"items": [], "codes": [], "color": 0x00ffff},
        "🚀【加速・トレンド追撃】": {"items": [], "codes": [], "color": 0x00ff00}
    }

    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False)
            cl, hi, lo, op, vo = data['Close'], data['High'], data['Low'], data['Open'], data['Volume']
            rsi_df = calculate_rsi(cl); psy_df = calculate_psychological(cl)
            r9_df = calculate_rci(cl, 9); r27_df = calculate_rci(cl, 27)
            
            for s in chunk:
                try:
                    c_s = cl[s].dropna(); p = c_s.iloc[-1]
                    if len(c_s) < 50 or p < PRICE_MIN: continue
                    if vo[s].tail(5).mean() < MIN_VOLUME_5D: continue
                    
                    r9_c, r9_p = r9_df[s].iloc[-1], r9_df[s].iloc[-2]
                    r27_c, r27_p = r27_df[s].iloc[-1], r27_df[s].iloc[-2]
                    psy_c = psy_df[s].iloc[-1]
                    sakata = get_sakata_signal(hi[s], lo[s], op[s], cl[s], vo[s])
                    
                    # 🌟 酒田サインがない銘柄はここで足切り（絞り込みの核心）
                    if not sakata: continue

                    code_num = s.replace(".T", "")
                    card = f"**{code_num} {name_map[s]}** (`{p:,.0f}円`)\n└ {sakata} | RCI9:{r9_c:.0f} Psy:{psy_c:.0f}\n"

                    # 超厳選判定
                    if (r9_p < r27_p and r9_c >= r27_c and r9_c < 0) and 30 <= psy_c <= 60:
                        categories["🏹【酒田×RCI 究極スナイプ】"]["items"].append(card)
                        categories["🏹【酒田×RCI 究極スナイプ】"]["codes"].append(code_num)
                    elif (psy_c >= 55 or r27_c > 80) and c_s.iloc[-1] > c_s.iloc[-2]:
                        categories["🚀【加速・トレンド追撃】"]["items"].append(card)
                        categories["🚀【加速・トレンド追撃】"]["codes"].append(code_num)
                except: continue
        except: continue
        time.sleep(1)

    for cat, data in categories.items():
        if data["items"]:
            send_discord("\n".join(data["items"][:15]) + f"\n**📌 コピペ用**\n`{','.join(data['codes'])}`" , title=cat, color=data["color"])

if __name__ == "__main__":
    main()
