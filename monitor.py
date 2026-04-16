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
    content = f"### 🤖 AIプロの売買助言\n> {text}" if is_ai else f"# {title}\n{text}"
    try:
        for i in range(0, len(content), 1950):
            requests.post(DISCORD_URL, json={"content": content[i:i+1950]}, timeout=10)
            time.sleep(1)
    except Exception as e: print(f"Discordエラー: {e}")

def get_ai_insight(msg_text):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = f"日本株プロとして、DMIの反転やRCIのクロスを考慮し、以下の銘柄リストから1つ厳選して買い時を100字以内で述べよ:\n{msg_text}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=12)
        return res.json()["candidates"][0]["content"]["parts"][0]["text"] if res.status_code == 200 else None
    except: return None

def main():
    if is_market_holiday(): return
    print(f"🚀 RCI & DMI ハイブリッドスキャン開始...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    # 🌟 番号のみを保存するためのリストも追加
    categories = {
        "🔥【DMI: GC】(上昇確定)": {"items": [], "codes": []},
        "✨【RCI: GC】(底値反転)": {"items": [], "codes": []},
        "🐣【DMI: 反転開始】(初動)": {"items": [], "codes": []},
        "💀【デッドクロス注意】": {"items": [], "codes": []}
    }
    
    chunk_size = 80
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False)
            close_df, high_df, low_df = data['Close'], data['High'], data['Low']
            rci9_df = get_rci_vectorized(close_df, 9)
            rci26_df = get_rci_vectorized(close_df, 26)
            rsi_df = get_rsi_vectorized(close_df, 14)

            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    if len(c) < 30 or c.iloc[-1] < PRICE_MIN: continue
                    
                    h, l, cl = high_df[s], low_df[s], close_df[s]
                    tr = pd.concat([(h-l), (h-cl.shift(1)).abs(), (l-cl.shift(1)).abs()], axis=1).max(axis=1).rolling(14).sum()
                    pdm = pd.Series(np.where((h.diff()>l.diff().abs())&(h.diff()>0), h.diff(), 0), index=h.index).rolling(14).sum()
                    mdm = pd.Series(np.where((l.diff().abs()>h.diff())&(l.diff()>0), l.diff().abs(), 0), index=h.index).rolling(14).sum()
                    p_di, m_di = (pdm / tr) * 100, (mdm / tr) * 100
                    adx = ((p_di - m_di).abs() / (p_di + m_di) * 100).rolling(14).mean()
                    
                    p_curr, p_prev = p_di.iloc[-1], p_di.iloc[-2]
                    m_curr, m_prev = m_di.iloc[-1], m_di.iloc[-2]
                    a_curr = adx.iloc[-1]
                    r9_curr, r9_prev = rci9_df[s].iloc[-1], rci9_df[s].iloc[-2]
                    r26_curr, r26_prev = rci26_df[s].iloc[-1], rci26_df[s].iloc[-2]

                    code_num = s.replace('.T','')
                    stock_card = (
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"**{code_num} : {name_map[s]}**\n"
                        f"┣ 株価: `{cl.iloc[-1]:,.0f}円` | RSI: `{rsi_df[s].iloc[-1]:.0f}`\n"
                        f"┗ RCI9: `{r9_curr:.0f}` | +DI: `{p_curr:.1f}` | ADX: `{a_curr:.1f}`\n"
                    )

                    # 判定と保存
                    if p_prev <= m_prev and p_curr > m_curr:
                        categories["🔥【DMI: GC】(上昇確定)"]["items"].append(stock_card)
                        categories["🔥【DMI: GC】(上昇確定)"]["codes"].append(code_num)
                    elif p_curr > p_prev and p_curr < 20 and a_curr < 25:
                        categories["🐣【DMI: 反転開始】(初動)"]["items"].append(stock_card)
                        categories["🐣【DMI: 反転開始】(初動)"]["codes"].append(code_num)
                    
                    if r9_prev <= r26_prev and r9_curr > r26_curr and r9_curr < 0:
                        categories["✨【RCI: GC】(底値反転)"]["items"].append(stock_card)
                        categories["✨【RCI: GC】(底値反転)"]["codes"].append(code_num)
                    
                    if r9_prev >= r26_prev and r9_curr < r26_curr and r9_curr > 50:
                        categories["💀【デッドクロス注意】"]["items"].append(stock_card)
                        categories["💀【デッドクロス注意】"]["codes"].append(code_num)

                except: continue
        except: continue
        time.sleep(1)

    ai_input = ""
    hit_any = False
    for cat_name, data in categories.items():
        if data["items"]:
            hit_any = True
            # 詳細リスト（5件）
            body = "".join(data["items"][:5]) + "━━━━━━━━━━━━━━━━━━"
            # 🌟 コピペ用番号リストを追加
            footer = f"\n**📌 コピペ用コード (番号のみ)**\n`{','.join(data['codes'])}`"
            send_discord(body + footer, title=cat_name)
            ai_input += f"【{cat_name}】\n" + data["items"][0]

    if hit_any:
        ai_msg = get_ai_insight(ai_input)
        if ai_msg: send_discord(ai_msg, is_ai=True)
    
    print("✅ 全工程完了")

if __name__ == "__main__":
    main()

