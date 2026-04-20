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
MIN_VOLUME_5D = 300000  # 取引活発な銘柄に絞り込み
PRICE_MIN = 500

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
        return {str(row['コード']) + ".T": f"{row['銘柄名']}({row['市場・商品区分'][:1]})" for _, row in target_df.iterrows()}
    except:
        return {"8035.T": "東エレク(プ)", "9984.T": "SBG(プ)", "7203.T": "トヨタ(プ)"}

# --- 指標計算 ---
def calculate_rci_vec(df, period):
    def _rci(x):
        n = len(x); d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(_rci)

def calculate_dmi_manual(h, l, c, p=14):
    pc = c.shift(1); tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1).rolling(p).sum()
    pdm = (np.where((h.diff()>l.diff().abs())&(h.diff()>0), h.diff(), 0)); pdm_s = pd.Series(pdm, index=h.index).rolling(p).sum()
    mdm = (np.where((l.diff().abs()>h.diff())&(l.diff()>0), l.diff().abs(), 0)); mdm_s = pd.Series(mdm, index=h.index).rolling(p).sum()
    pdi = (pdm_s / (tr + 1e-9)) * 100; mdi = (mdm_s / (tr + 1e-9)) * 100
    adx = ((pdi - mdi).abs() / (pdi + mdi + 1e-9) * 100).rolling(p).mean()
    return pdi, mdi, adx

def calculate_psychological_vec(df, period=12):
    return ((df.diff() > 0).astype(int).rolling(window=period).sum() / period) * 100

def check_sakata_signs(h, l, o, c, v):
    """酒田五法・上昇/下降の予兆検知"""
    signs = []
    # 赤三兵の予兆 (陽線2本 + 出来高増加)
    if (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-2] > o.iloc[-2]) and (c.iloc[-1] > c.iloc[-2]) and (v.iloc[-1] > v.iloc[-2]):
        signs.append("🔆赤三兵の予兆")
    # 窓開け上昇 (跳ね)
    if l.iloc[-1] > h.iloc[-2]:
        signs.append("✨窓開け上昇")
    # 黒三兵の予兆 (陰線2本)
    if (c.iloc[-1] < o.iloc[-1]) and (c.iloc[-2] < o.iloc[-2]) and (c.iloc[-1] < c.iloc[-2]):
        signs.append("⛈️黒三兵の予兆")
    return " ".join(signs)

def send_discord(text):
    if not text.strip(): return
    try:
        for i in range(0, len(text), 1900):
            requests.post(DISCORD_URL, json={"content": text[i:i+1900]}, timeout=10)
            time.sleep(1)
    except: pass

def main():
    if is_market_holiday(): return
    name_map = get_target_tickers(); tickers = list(name_map.keys())
    categories = {
        "🎯【最速狙撃】(RCI GC + Psy50)": [],
        "🔥【トレンド追撃】(DMI GC)": [],
        "🚀【加速・フル乗車】(Psy75+)": []
    }
    all_hit_codes = []  # 横並び用リスト

    chunk_size = 150
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False)
            cl_df, hi_df, lo_df, op_df, vo_df = data['Close'], data['High'], data['Low'], data['Open'], data['Volume']
            
            # マルチインデックス対策
            if isinstance(cl_df, pd.DataFrame) and isinstance(cl_df.columns, pd.MultiIndex):
                cl_df = cl_df.get_level_values(0)

            r9_df = calculate_rci_vec(cl_df, 9); r27_df = calculate_rci_vec(cl_df, 27)
            psy_df = calculate_psychological_vec(cl_df, 12)
            
            for s in chunk:
                try:
                    c = cl_df[s].dropna(); p = c.iloc[-1]
                    if len(c) < 50 or p < PRICE_MIN: continue
                    v = vo_df[s].dropna()
                    if v.tail(5).mean() < MIN_VOLUME_5D: continue
                    
                    p_di, m_di, adx = calculate_dmi_manual(hi_df[s], lo_df[s], cl_df[s])
                    r9_c, r9_p = r9_df[s].iloc[-1], r9_df[s].iloc[-2]
                    r27_c, r27_p = r27_df[s].iloc[-1], r27_df[s].iloc[-2]
                    psy_c = psy_df[s].iloc[-1]
                    pdi_c, pdi_p = p_di.iloc[-1], p_di.iloc[-2]
                    mdi_c, mdi_p = m_di.iloc[-1], m_di.iloc[-2]

                    # 酒田サイン確認
                    sakata = check_sakata_signs(hi_df[s], lo_df[s], op_df[s], cl_df[s], v)
                    
                    added = False
                    info = f"・{name_map[s]} ({s}) {p:,.0f}円 | Psy:{psy_c:.0f} {sakata}"
                    
                    # 勝利の法則 判定
                    if (r9_p < r27_p and r9_c >= r27_c and r9_c <= 0) and psy_c >= 50:
                        categories["🎯【最速狙撃】(RCI GC + Psy50)"].append(info); added = True
                    elif (pdi_p < mdi_p and pdi_c >= mdi_c) and psy_c >= 50:
                        categories["🔥【トレンド追撃】(DMI GC)"].append(info); added = True
                    elif psy_c >= 75 and r27_c > r27_p:
                        categories["🚀【加速・フル乗車】(Psy75+)"].append(info); added = True
                    
                    if added:
                        all_hit_codes.append(s.replace(".T", ""))
                except: continue
        except: continue
        time.sleep(1)

    # 通知送信
    for cat, items in categories.items():
        if items:
            send_discord(f"**{cat}**\n" + "\n".join(items[:15]))

    if all_hit_codes:
        # 重複を排除して横並び
        unique_codes = sorted(list(set(all_hit_codes)))
        copy_paste_text = "📋 **Streamlit診断用リスト**\n```text\n" + ",".join(unique_codes) + "\n```"
        send_discord(copy_paste_text)
    else:
        send_discord("🔍 本日は厳選条件に合致する銘柄はありませんでした。")

if __name__ == "__main__":
    main()
