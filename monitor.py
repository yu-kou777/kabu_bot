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

# --- インジケーター計算関数 ---
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

def get_dmi_vectorized(high_df, low_df, close_df, period=14):
    up_move = high_df.diff()
    down_move = low_df.diff().abs()
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    tr1 = high_df - low_df
    tr2 = (high_df - close_df.shift(1)).abs()
    tr3 = (low_df - close_df.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1) # 本来は銘柄ごとだが簡易化
    # ※ベクトル化計算のため実際には銘柄ごとにループ処理
    return plus_dm, minus_dm, tr

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
    
    categories = {
        "🔥【DMI: ゴールデンクロス】(上昇確定)": [],
        "✨【RCI: ゴールデンクロス】(底値反転)": [],
        "🐣【DMI: 反転開始】(初動・低位並び)": [],
        "💀【デッドクロス注意】": []
    }
    
    chunk_size = 80
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False)
            close_df, high_df, low_df, vol_df = data['Close'], data['High'], data['Low'], data['Volume']
            
            # 各指標計算
            rci9_df = get_rci_vectorized(close_df, 9)
            rci26_df = get_rci_vectorized(close_df, 26)
            rsi_df = get_rsi_vectorized(close_df, 14)

            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    if len(c) < 30 or c.iloc[-1] < PRICE_MIN: continue
                    
                    # DMI個別計算 (14日)
                    h, l, cl = high_df[s], low_df[s], close_df[s]
                    tr = pd.concat([(h-l), (h-cl.shift(1)).abs(), (l-cl.shift(1)).abs()], axis=1).max(axis=1).rolling(14).sum()
                    pdm = (np.where((h.diff()>l.diff().abs())&(h.diff()>0), h.diff(), 0))
                    pdm_s = pd.Series(pdm, index=h.index).rolling(14).sum()
                    mdm = (np.where((l.diff().abs()>h.diff())&(l.diff()>0), l.diff().abs(), 0))
                    mdm_s = pd.Series(mdm, index=h.index).rolling(14).sum()
                    
                    p_di = (pdm_s / tr) * 100
                    m_di = (mdm_s / tr) * 100
                    dx = (p_di - m_di).abs() / (p_di + m_di) * 100
                    adx = dx.rolling(14).mean()
                    
                    # 現在値と前日値
                    p_curr, p_prev = p_di.iloc[-1], p_di.iloc[-2]
                    m_curr, m_prev = m_di.iloc[-1], m_di.iloc[-2]
                    a_curr, a_prev = adx.iloc[-1], adx.iloc[-2]
                    
                    r9_curr, r9_prev = rci9_df[s].iloc[-1], rci9_df[s].iloc[-2]
                    r26_curr, r26_prev = rci26_df[s].iloc[-1], rci26_df[s].iloc[-2]

                    # --- 判定ロジック ---
                    dmi_msg = ""
                    # 1. DMIゴールデンクロス (+DIが-DIを上抜く)
                    is_dmi_gc = (p_prev <= m_prev and p_curr > m_curr)
                    # 2. DMI反転開始 (+DIが上昇 & 低位並び)
                    is_dmi_reversal = (p_curr > p_prev and p_curr < 20 and a_curr < 25)
                    # 3. RCIゴールデンクロス
                    is_rci_gc = (r9_prev <= r26_prev and r9_curr > r26_curr and r9_curr < 0)
                    # 4. デッドクロス (RCIまたはDMI)
                    is_dc = (r9_prev >= r26_prev and r9_curr < r26_curr) or (p_prev >= m_prev and p_curr < m_curr)

                    stock_card = (
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"**{s.replace('.T','')} : {name_map[s]}**\n"
                        f"┣ 株価: `{cl.iloc[-1]:,.0f}円` | RSI: `{rsi_df[s].iloc[-1]:.0f}`\n"
                        f"┗ RCI9: `{r9_curr:.0f}` | +DI: `{p_curr:.1f}` | ADX: `{a_curr:.1f}`\n"
                    )

                    if is_dmi_gc: categories["🔥【DMI: ゴールデンクロス】(上昇確定)"].append((p_curr, stock_card))
                    elif is_dmi_reversal: categories["🐣【DMI: 反転開始】(初動・低位並び)"].append((p_curr, stock_card))
                    if is_rci_gc: categories["✨【RCI: ゴールデンクロス】(底値反転)"].append((r9_curr, stock_card))
                    if is_dc and r9_curr > 50: categories["💀【デッドクロス注意】"].append((r9_curr, stock_card))

                except: continue
        except: continue
        time.sleep(1)

    ai_input = ""
    hit_any = False
    for cat_name, items in categories.items():
        if items:
            hit_any = True
            sorted_items = sorted(items, key=lambda x: x[0], reverse=True)[:5]
            display_text = "".join([x[1] for x in sorted_items]) + "━━━━━━━━━━━━━━━━━━"
            send_discord(display_text, title=cat_name)
            ai_input += f"【{cat_name}】\n" + sorted_items[0][1]

    if hit_any:
        ai_msg = get_ai_insight(ai_input)
        if ai_msg: send_discord(ai_msg, is_ai=True)
    
    print("✅ 全工程完了")

if __name__ == "__main__":
    main()
