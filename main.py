import os
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
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSyBUiTPV-0yOXIDzgydV4NoArJkBufJSpys")
DISCORD_URL = os.environ.get("DISCORD_URL", "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX")

PRICE_MIN = 3001       # 呼値5円以上（株価3,001円以上）の値がさ株限定

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

# --- 📊 指標計算関数 ---
def calculate_rci(df, period):
    def _rci(x):
        n = len(x); d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(_rci)

def calculate_psychological(df, period=12):
    return ((df.diff() > 0).astype(int).rolling(window=period).sum() / period) * 100

def calculate_dmi_custom(high_df, low_df, close_df, di_period=14, adx_period=9):
    up_move = high_df.diff(); down_move = -low_df.diff()
    dm_pos = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    dm_neg = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr1 = high_df - low_df
    tr2 = (high_df - close_df.shift()).abs()
    tr3 = (low_df - close_df.shift()).abs()
    tr = pd.DataFrame(np.max([tr1, tr2, tr3], axis=0), index=close_df.index, columns=close_df.columns)
    atr = tr.rolling(window=di_period).mean()
    plus_di = (pd.DataFrame(dm_pos, index=close_df.index, columns=close_df.columns).rolling(window=di_period).mean() / (atr + 1e-9)) * 100
    minus_di = (pd.DataFrame(dm_neg, index=close_df.index, columns=close_df.columns).rolling(window=di_period).mean() / (atr + 1e-9)) * 100
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9) * 100
    adx = dx.rolling(window=adx_period).mean()
    return plus_di, minus_di, adx

def send_discord_raw(payload):
    try:
        res = requests.post(DISCORD_URL, json=payload, timeout=15)
        return res.status_code in [200, 204]
    except: return False

# --- 🚀 メインロジック ---
def main():
    if is_market_holiday(): return

    tz = pytz.timezone('Asia/Tokyo')
    current_hour = datetime.now(tz).hour
    
    if current_hour < 13:
        timing_title = "【前場・11:00中間巡回】"
        vol_today_multiplier = 0.4
    else:
        timing_title = "【後場・16:00大引確定】"
        vol_today_multiplier = 1.2   # 1.5倍から1.2倍にマイルド化

    print(f"🚀 {timing_title} スキャン開始...")
    name_map = get_target_tickers(); tickers = list(name_map.keys())
    
    categories = {
        "rule1": {"title": f"🎯{timing_title}・テス流 王道押し目買い (RCI反転)", "items": [], "codes": [], "color": 0x00ffff},
        "rule2": {"title": f"💎{timing_title}・マスピ2 大底売られすぎ (Psy低位)", "items": [], "codes": [], "color": 0xff3333},
        "rule3": {"title": f"📈{timing_title} =DMIトレンド初動 (クロス・接近)=", "items": [], "codes": [], "color": 0x00ff00}
    }

    chunk_size = 80  
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False)
            cl, hi, lo = data['Close'], data['High'], data['Low']
            vo = data['Volume']
            
            r9_df = calculate_rci(cl, 9).ffill().bfill()
            r27_df = calculate_rci(cl, 27).ffill().bfill()
            psy_df = calculate_psychological(cl, 12).ffill().bfill()
            plus_di, minus_di, _ = calculate_dmi_custom(hi, lo, cl)
            
            for s in chunk:
                try:
                    c_s = cl[s].dropna(); v_s = vo[s].dropna()
                    if len(c_s) < 65 or c_s.iloc[-1] < PRICE_MIN: continue  
                    
                    # ーーー 🛠️ 出来高トリプルフィルター（毎日ヒット調整版） ーーー
                    vol_3m_avg = v_s.iloc[-60:].mean()          
                    vol_today = v_s.iloc[-1]                     
                    vol_5d_avg = v_s.iloc[-5:].mean()            
                    
                    if vol_3m_avg < 500000: continue             # 平均50万株
                    if vol_today < (vol_3m_avg * vol_today_multiplier): continue   # 当日1.2倍
                    if vol_5d_avg < (vol_3m_avg * 1.0): continue  # 5日平均
                    
                    p = c_s.iloc[-1]
                    r9_c, r9_p = r9_df[s].iloc[-1], r9_df[s].iloc[-2]
                    r27_c, r27_p = r27_df[s].iloc[-1], r27_df[s].iloc[-2]
                    psy_c, psy_p = psy_df[s].iloc[-1], psy_df[s].iloc[-2]
                    pdi_c, pdi_p = plus_di[s].iloc[-1], plus_di[s].iloc[-2]
                    mdi_c, mdi_p = minus_di[s].iloc[-1], minus_di[s].iloc[-2]
                    
                    code_num = s.replace(".T", "")
                    vol_ratio = vol_today / vol_3m_avg
                    yobine_label = "5円単位" if p <= 5000 else "10円単位" if p <= 30000 else "50円単位〜"

                    card = (f"**{code_num} {name_map[s]}** (`{p:,.0f}円` / {yobine_label}) 出来高:{vol_ratio:.2f}倍\n"
                            f"└ RCI9:`{r9_c:.0f}` | RCI27:`{r27_c:.0f}` | Psy:`{psy_c:.0f}` | +DI:`{pdi_c:.0f}`\n")

                    # ーーー 🎯 トモユキ式・新3大条件判定 ーーー
                    # 【ルール1】王道押し目買い：長期が壁(-50以上)を維持し、短期が底から反転
                    if r27_c >= -50 and r9_p < r9_c and r9_p <= -40:
                        categories["rule1"]["items"].append(card)
                        categories["rule1"]["codes"].append(code_num)
                        
                    # 【ルール2】大底売られすぎ：短期がディープ底、かつサイコロが売られすぎ
                    elif r9_c <= -75 and psy_c <= 35:
                        categories["rule2"]["items"].append(card)
                        categories["rule2"]["codes"].append(code_num)
                        
                    # 【ルール3】DMIトレンド初動：+DIと-DIのゴールデンクロス、または超接近(差が3%以内)
                    elif (pdi_p <= mdi_p and pdi_c > mdi_c) or (abs(pdi_c - mdi_c) <= 3.0 and pdi_c > pdi_p):
                        categories["rule3"]["items"].append(card)
                        categories["rule3"]["codes"].append(code_num)

                except: continue
        except: continue
        time.sleep(1)

    # ーーー 📨 Discord送信 ーーー
    send_count = 0
    for key, data in categories.items():
        if data["items"]:
            body = "\n".join(data["items"][:10]) # 1カテゴリ最大10件表示
            footer = f"\n**📌 コピペ用コード (番号のみ)**\n`{','.join(data['codes'])}`"
            payload = {"embeds": [{"title": data["title"], "description": body + footer, "color": data["color"], "timestamp": datetime.now().isoformat()}]}
            if send_discord_raw(payload): send_count += 1
            time.sleep(1)

    if send_count == 0:
        empty_title = f"ℹ️ {timing_title}・定期巡回完了報告"
        empty_message = "本日は3つの拡張ルール（押し目・大底・DMI）のすべてにおいて、呼値5円以上かつ出来高クリアの銘柄はありませんでした。"
        payload = {"embeds": [{"title": empty_title, "description": empty_message, "color": 0x95a5a6, "timestamp": datetime.now().isoformat()}]}
        send_discord_raw(payload)

if __name__ == "__main__":
    main()
