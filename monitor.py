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
MIN_VOLUME_5D = 100000 
PRICE_MIN = 500 

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo'); now = datetime.now(tz)
    return now.weekday() >= 5 or jpholiday.is_holiday(now.date())

def get_target_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        target_df = df[df['市場・商品区分'].str.contains('プライム|スタンダード', na=False)]
        return {str(row['コード']) + ".T": f"{row['銘柄名']}({row['市場・商品区分'][:1]})" for _, row in target_df.iterrows()}
    except: return {"8035.T": "東エレク(プ)", "9984.T": "SBG(プ)", "7203.T": "トヨタ(プ)"}

def calculate_rci_vec(df, period):
    def _rci(x):
        n = len(x); d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(_rci)

def calculate_dmi_manual(h, l, c, p=14):
    pc = c.shift(1); tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1).rolling(p).sum()
    pdm = (np.where((h.diff()>l.diff().abs())&(h.diff()>0), h.diff(), 0)); pdm_s = pd.Series(pdm, index=h.index).rolling(p).sum()
    mdm = (np.where((l.diff().abs()>h.diff())&(l.diff()>0), l.diff().abs(), 0)); mdm_s = pd.Series(mdm, index=h.index).rolling(p).sum()
    pdi = (pdm_s / tr) * 100; mdi = (mdm_s / tr) * 100
    adx = ((pdi - mdi).abs() / (pdi + mdi) * 100).rolling(p).mean()
    return pdi, mdi, adx

def calculate_psychological_vec(df, period=12):
    return ((df.diff() > 0).astype(int).rolling(window=period).sum() / period) * 100

def send_discord(text):
    if not text.strip(): return
    try:
        for i in range(0, len(text), 1900):
            requests.post(DISCORD_URL, json={"content": text[i:i+1900]}, timeout=10)
            time.sleep(1)
    except: pass

def get_ai_insight(msg_text):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = f"日本株プロとして、友幸氏の戦略（RCI GC→DMI GC→Psy75）に基づき、以下の銘柄から1つ厳選し、買い増しや保持の助言を100字以内で述べよ:\n{msg_text}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        return res.json()['candidates'][0]['content']['parts'][0]['text']
    except: return "AI分析リミットです。"

def main():
    if is_market_holiday(): return
    name_map = get_target_tickers(); tickers = list(name_map.keys())
    categories = {
        "🎯【最速狙撃】(RCI GC + Psy50)": [],
        "🔥【トレンド追撃】(DMI GC)": [],
        "🚀【加速・フル乗車】(Psy75+)": [],
        "🛑【撤退・警告】(RCI DC/Psy50割)": []
    }
    
    chunk_size = 150
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False)
            cl_df, hi_df, lo_df, vo_df = data['Close'], data['High'], data['Low'], data['Volume']
            r9_df = calculate_rci_vec(cl_df, 9); r27_df = calculate_rci_vec(cl_df, 27)
            psy_df = calculate_psychological_vec(cl_df, 12)
            
            for s in chunk:
                try:
                    c = cl_df[s].dropna(); p = c.iloc[-1]
                    if len(c) < 50 or p < PRICE_MIN: continue
                    if vo_df[s].tail(5).mean() < MIN_VOLUME_5D: continue
                    
                    p_di, m_di, adx = calculate_dmi_manual(hi_df[s], lo_df[s], cl_df[s])
                    r9_c, r9_p = r9_df[s].iloc[-1], r9_df[s].iloc[-2]
                    r27_c, r27_p = r27_df[s].iloc[-1], r27_df[s].iloc[-2]
                    psy_c, psy_p = psy_df[s].iloc[-1], psy_df[s].iloc[-2]
                    pdi_c, pdi_p = p_di.iloc[-1], p_di.iloc[-2]
                    mdi_c, mdi_p = m_di.iloc[-1], m_di.iloc[-2]

                    info = f"・{name_map[s]} ({s}) {p:,.0f}円 | Psy:{psy_c:.0f} / RCI9:{r9_c:.0f}"
                    
                    if (r9_p < r27_p and r9_c >= r27_c and r9_c <= 0) and psy_c >= 50:
                        categories["🎯【最速狙撃】(RCI GC + Psy50)"].append(info)
                    elif (pdi_p < mdi_p and pdi_c >= mdi_c) and psy_c >= 50:
                        categories["🔥【トレンド追撃】(DMI GC)"].append(info)
                    elif psy_c >= 75 and r27_c > r27_p:
                        categories["🚀【加速・フル乗車】(Psy75+)"].append(info)
                    elif r27_c < r27_p and r9_c < r27_c and r9_c > 50:
                        categories["🛑【撤退・警告】(RCI DC/Psy50割)"].append(info)
                except: continue
        except: continue
        time.sleep(1)

    has_hit = False; ai_text = ""
    for cat, items in categories.items():
        if items:
            has_hit = True; msg = f"**{cat}**\n" + "\n".join(items[:15])
            send_discord(msg); ai_text += f"{cat}\n" + "\n".join(items[:2]) + "\n"

    if has_hit:
        ai_msg = get_ai_insight(ai_text); send_discord(f"🤖 **【AI 勝利の法則・攻略本】**\n{ai_msg}")
    else:
        send_discord("🔍 本日は法則に合致する銘柄はありませんでした。")

if __name__ == "__main__":
    main()
