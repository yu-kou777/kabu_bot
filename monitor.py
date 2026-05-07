import yfinance as yf
import pandas as pd
import requests
import time
import numpy as np
import io
from datetime import datetime
import pytz
import jpholiday

# --- ⚙️ 設定（トモユキさんの情報を維持） ---
GEMINI_KEY = "AIzaSyBUiTPV-0yOXIDzgydV4NoArJkBufJSpys"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

# フィルター条件
MIN_VOLUME_5D = 300000  # 出来高の少ない銘柄は「だまし」が多いのでカット
PRICE_MIN = 300         # 低位株も含める設定

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    return now.weekday() >= 5 or jpholiday.is_holiday(now.date())

def get_target_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        target_df = df[df['市場・商品区分'].str.contains('プライム|スタンダード', na=False)]
        return {str(row['コード']) + ".T": f"{row['銘柄名']}" for _, row in target_df.iterrows()}
    except:
        return {"8035.T": "東エレク", "9984.T": "SBG", "6834.T": "精工技研"}

# --- 📊 指標計算ユニット ---
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

def get_sakata_signal(h, l, o, c):
    """酒田五法フィルター：ローソク足の形で最終判断"""
    s = []
    # 1. 赤三兵（上昇の継続・初動）
    if (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-2] > o.iloc[-2]) and (c.iloc[-3] > o.iloc[-3]) and (c.iloc[-1] > c.iloc[-2]):
        s.append("🔆赤三兵")
    # 2. 陽の包み足（底値からの反転）
    if (c.iloc[-2] < o.iloc[-2]) and (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-1] >= o.iloc[-2]):
        s.append("🔥陽の包み足")
    # 3. 上放れ窓（勢い加速）
    if l.iloc[-1] > h.iloc[-2]:
        s.append("✨上放れ窓")
    # 4. 明けの明星
    if (c.iloc[-3] < o.iloc[-3]) and (abs(c.iloc[-2] - o.iloc[-2]) < abs(c.iloc[-3] - o.iloc[-3]) * 0.2) and (c.iloc[-1] > o.iloc[-1]):
        s.append("🌅明けの明星")
    return " ".join(s)

def send_discord(text, title=None, color=0x2ecc71):
    if not text.strip(): return
    payload = {"embeds": [{"title": title, "description": text, "color": color, "timestamp": datetime.now().isoformat()}]}
    try:
        requests.post(DISCORD_URL, json=payload, timeout=10)
        time.sleep(1)
    except: pass

# --- 🚀 巡回メインロジック ---
def main():
    if is_market_holiday():
        print("☕ 休場日です。")
        return

    print("🚀 Sniper Patrol Start...")
    name_map = get_target_tickers(); tickers = list(name_map.keys())
    
    categories = {
        "🎯【テス流・最速狙撃】(RCI GC × 酒田)": {"items": [], "codes": [], "color": 0x00ffff},
        "🔥【追撃・トレンド加速】(Psy上昇 × VWAP)": {"items": [], "codes": [], "color": 0x00ff00},
        "🛑【下落警戒・利確】(RCI DC)": {"items": [], "codes": [], "color": 0xff0000}
    }

    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False)
            cl, hi, lo, op, vo = data['Close'], data['High'], data['Low'], data['Open'], data['Volume']
            
            # 指標一括計算
            r9_df, r27_df = calculate_rci(cl, 9), calculate_rci(cl, 27)
            psy_df = calculate_psychological(cl, 12)
            
            for s in chunk:
                try:
                    c_s = cl[s].dropna(); p = c_s.iloc[-1]
                    if len(c_s) < 50 or p < PRICE_MIN: continue
                    if vo[s].tail(5).mean() < MIN_VOLUME_5D: continue
                    
                    r9_c, r9_p = r9_df[s].iloc[-1], r9_df[s].iloc[-2]
                    r27_c, r27_p = r27_df[s].iloc[-1], r27_df[s].iloc[-2]
                    psy_c = psy_df[s].iloc[-1]
                    vwap_c = calculate_vwap(data.xs(s, level=1, axis=1) if isinstance(data.columns, pd.MultiIndex) else data).iloc[-1]
                    sakata = get_sakata_signal(hi[s], lo[s], op[s], cl[s])
                    
                    code_num = s.replace(".T", "")
                    card = f"**{code_num} {name_map[s]}** (`{p:,.0f}円`)\n└ {sakata if sakata else '形:静観'} | RCI9:{r9_c:.0f} Psy:{psy_c:.0f}\n"

                    # 1. 最速狙撃（RCIクロス ＋ 酒田サインあり）
                    if (r9_p < r27_p and r9_c >= r27_c and r9_c < 0) and sakata:
                        categories["🎯【テス流・最速狙撃】(RCI GC × 酒田)"]["items"].append(card)
                        categories["🎯【テス流・最速狙撃】(RCI GC × 酒田)"]["codes"].append(code_num)
                    
                    # 2. 追撃（VWAP突破 ＋ 強気サイコロ）
                    elif (p > vwap_c and cl[s].iloc[-2] <= vwap_c) or (psy_c >= 55 and r9_c > r9_p):
                        categories["🔥【追撃・トレンド加速】(Psy上昇 × VWAP)"]["items"].append(card)
                        categories["🔥【追撃・トレンド加速】(Psy上昇 × VWAP)"]["codes"].append(code_num)
                    
                    # 3. 利確・空売り（RCIデッドクロス ＋ 高値圏）
                    elif (r9_p > r27_p and r9_c <= r27_c and r9_c > 70):
                        categories["🛑【利確・空売り】(RCI DC)"]["items"].append(card)
                        categories["🛑【利確・空売り】(RCI DC)"]["codes"].append(code_num)

                except: continue
        except: continue
        time.sleep(1)

    # Discord送信
    for cat, data in categories.items():
        if data["items"]:
            # 上位15件に絞って送信
            body = "\n".join(data["items"][:15])
            # 🌟 コピペ用番号リスト
            footer = f"\n**📌 コピペ用コード (番号のみ)**\n`{','.join(data['codes'])}`"
            send_discord(body + footer, title=cat, color=data["color"])

    print("✅ Patrol Complete")

if __name__ == "__main__":
    main()
