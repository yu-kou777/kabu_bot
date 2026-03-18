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

VOLATILITY_THRESHOLD = 0.035 
PRICE_MIN = 500
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
        return {"7203.T": "トヨタ", "8306.T": "三菱UFJ", "9984.T": "SBG"}

def get_rci_vectorized(df, period):
    """RCI(順位相関係数)のベクトル計算"""
    def _rci(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(_rci)

def send_discord(text, title=None):
    if not text.strip(): return
    content = f"**【{title}】**\n{text}" if title else text
    try:
        requests.post(DISCORD_URL, json={"content": content}, timeout=10)
        time.sleep(1.2)
    except Exception as e:
        print(f"Discord送信エラー: {e}")

def get_ai_insight(msg_text):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = f"日本株プロとしてRCIとVWAPから厳選1銘柄の買い時/売り時を100字以内で述べよ:\n{msg_text}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        return None
    except:
        return None

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print("🚀 スキャン開始（RCI・VWAP判定モード）...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    selected_list = []
    
    chunk_size = 100
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False, threads=True)
            close_df = data['Close']
            vol_df = data['Volume']
            high_df = data['High']
            low_df = data['Low']
            
            # 指標計算
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
                    # 25日VWAP計算
                    v_sum = v.tail(25).sum()
                    vwap25 = cv_df[s].tail(25).sum() / v_sum if v_sum > 0 else p
                    kairi = ((p - vwap25) / vwap25) * 100
                    
                    rci9 = rci9_df[s].iloc[-1]
                    rci26 = rci26_df[s].iloc[-1]
                    
                    # 判定ロジック
                    judge = "ーー"
                    if rci9 <= -80 and rci26 <= -50:
                        judge = "🔵買い時(底圏)"
                    elif rci9 >= 80 and rci26 >= 50:
                        judge = "🔴売り時(天圏)"
                    elif rci9 > rci9_df[s].iloc[-2] and rci9_df[s].iloc[-2] < -80:
                        judge = "✨反転(買い)"
                    
                    vol = (high_df[s].tail(5).max() - low_df[s].tail(5).min()) / p
                    
                    if vol >= VOLATILITY_THRESHOLD:
                        info = f"・{name_map[s]} ({s})\n   価:{p:,.0f}円 | VWAP乖離:{kairi:+.1f}%\n   RCI9:{rci9:.0f} / RCI26:{rci26:.0f}\n   判定: **{judge}**"
                        selected_list.append({"info": info, "rci9": rci9, "kairi": kairi})
                except: continue
        except: continue
        time.sleep(1)

    if selected_list:
        # VWAP乖離がマイナス（売られすぎ）かつRCIが低い順にソート（買いチャンス優先）
        sorted_list = sorted(selected_list, key=lambda x: x['kairi'])
        display_text = "\n".join([x['info'] for x in sorted_list[:12]])
        
        send_discord(display_text, title="📊 RCI & VWAP 厳選リスト")
        
        # AI分析（バックアップ付き）
        print("🤖 分析中...")
        ai_msg = get_ai_insight(display_text[:600])
        if ai_msg:
            send_discord(ai_msg, title="🤖 AIプロの売買助言")
        else:
            best = sorted_list[0]
            send_discord(f"【本日の本命】\n{best['info']}\n理由: VWAP乖離が最も大きく、RCIも底圏。反発期待値が高い。", title="⚙️ システム自動選定")
    else:
        send_discord("該当なし", title="🔍 スキャン完了")

    print("✅ 完了")

if __name__ == "__main__":
    main()
