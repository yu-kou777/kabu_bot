import yfinance as yf
import pandas as pd
import requests
import time
import numpy as np
import io
from datetime import datetime
import pytz
import jpholiday

# --- ⚙️ 設定（テス流・スイング最適化仕様） ---
GEMINI_KEY = "AIzaSyBUiTPV-0yOXIDzgydV4NoArJkBufJSpys"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

PRICE_MIN = 300  # 低位株カット

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

# --- 📊 テクニカル指標計算ユニット（マスピ2完全準拠） ---
def calculate_rci(df, period):
    def _rci(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(_rci)

def calculate_psychological(df, period=12):
    return ((df.diff() > 0).astype(int).rolling(window=period).sum() / period) * 100

def calculate_dmi_custom(high_df, low_df, close_df, di_period=14, adx_period=9):
    """マスピ2設定：DI=14, ADX=9 に準拠したDMI計算"""
    up_move = high_df.diff()
    down_move = -low_df.diff()
    
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

def send_discord(text, title=None, color=0x2ecc71):
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

    tz = pytz.timezone('Asia/Tokyo')
    current_hour = datetime.now(tz).hour
    
    if current_hour < 13:
        timing_title = "【前場・11:00中間巡回】"
        vol_today_multiplier = 0.4  # 取引時間2時間でのペース換算
    else:
        timing_title = "【後場・16:00大引確定】"
        vol_today_multiplier = 1.2  # 大引け時点で1.5倍以上

    print(f"🚀 {timing_title} テス流・スイングパトロール開始(出来高緩和版)...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    categories = {
        "buy_signal": {
            "title": f"🔥{timing_title}・スイング大底反転 (即買い候補)",
            "items": [], "codes": [], "color": 0xff3366
        },
        "forecast_signal": {
            "title": f"📈{timing_title}・反転予兆 (DMI接近 × 底圏維持)",
            "items": [], "codes": [], "color": 0x3399ff
        }
    }

    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False)
            cl, hi, lo, vo = data['Close'], data['High'], data['Low'], data['Volume']
            
            r9_df, r27_df = calculate_rci(cl, 9), calculate_rci(cl, 27)
            psy_df = calculate_psychological(cl, 12)
            plus_di_df, minus_di_df, adx_df = calculate_dmi_custom(hi, lo, cl)
            
            for s in chunk:
                try:
                    c_s = cl[s].dropna()
                    v_s = vo[s].dropna()
                    if len(c_s) < 65 or c_s.iloc[-1] < PRICE_MIN: continue
                    
                    vol_3m_avg = v_s.iloc[-60:].mean()
                    vol_today = v_s.iloc[-1]
                    vol_5d_avg = v_s.iloc[-5:].mean()
                    
                    if vol_3m_avg < 300000: continue
                    if vol_today < (vol_3m_avg * vol_today_multiplier): continue
                    if vol_5d_avg < (vol_3m_avg * 1.0): continue
                    
                    p = c_s.iloc[-1]
                    r9_c, r9_p = r9_df[s].iloc[-1], r9_df[s].iloc[-2]
                    r27_c = r27_df[s].iloc[-1]
                    psy_c, psy_p = psy_df[s].iloc[-1], psy_df[s].iloc[-2]
                    
                    p_di_c, p_di_p = plus_di_df[s].iloc[-1], plus_di_df[s].iloc[-2]
                    m_di_c, m_di_p = minus_di_df[s].iloc[-1], minus_di_df[s].iloc[-2]
                    
                    dmi_approaching = (p_di_c > p_di_p) and (m_di_c < m_di_p) and (p_di_c < m_di_c)
                    
                    code_num = s.replace(".T", "")
                    vol_ratio = vol_today / vol_3m_avg
                    
                    card = (f"**{code_num} {name_map[s]}** (`{p:,.0f}円`) 出来高:{vol_ratio:.2f}倍\n"
                            f"└ RCI9: `{r9_c:.0f}`(前`{r9_p:.0f}`) | RCI27: `{r27_c:.0f}` | Psy: `{psy_c:.0f}`\n")

                    is_rci_turn_up = (r9_p <= -85 and r9_c > r9_p) or (r9_p <= -50 and r9_c >= -50)
                    is_psy_turn_up = (psy_p <= 25 and psy_c > psy_p) or (psy_c >= 30 and psy_p <= 30)
                    
                    if (r27_c >= -50) and is_rci_turn_up and is_psy_turn_up:
                        categories["buy_signal"]["items"].append(card)
                        categories["buy_signal"]["codes"].append(code_num)
                    elif (r9_c <= -80) and (25 <= psy_c <= 35) and dmi_approaching:
                        categories["forecast_signal"]["items"].append(card)
                        categories["forecast_signal"]["codes"].append(code_num)

                except: continue
        except: continue
        time.sleep(1)

    total_found = len(categories["buy_signal"]["items"]) + len(categories["forecast_signal"]["items"])

    if total_found > 0:
        for key, data in categories.items():
            if data["items"]:
                body = "\n".join(data["items"][:15])
                footer = f"\n**📌 コピペ用コード (番号のみ)**\n`{','.join(data['codes'])}`"
                send_discord(body + footer, title=data["title"], color=data["color"])
    else:
        empty_title = f"ℹ️ {timing_title}・定期巡回報告"
        empty_message = "今回のスクリーニングにおいて、設定条件に合致するスイング候補銘柄はありませんでした。\n\n※システムおよび出来高トリプルフィルターは正常に機能しています。"
        send_discord(empty_message, title=empty_title, color=0x95a5a6)

    print("✅ パトロール完了")

if __name__ == "__main__":
    main()
