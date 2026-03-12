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
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
MIN_VOLUME_5D = 100000 
PRICE_MIN = 500 

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    if now.weekday() >= 5 or jpholiday.is_holiday(now.date()):
        return True
    return False

def get_target_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        target_df = df[df['市場・商品区分'].str.contains('プライム|スタンダード', na=False)]
        return {str(row['コード']) + ".T": f"{row['銘柄名']}({row['市場・商品区分'][:1]})" for _, row in target_df.iterrows()}
    except:
        return {"8035.T": "東エレク(プ)", "9984.T": "SBG(プ)", "7203.T": "トヨタ(プ)"}

def get_rsi_vectorized(df, period):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss + 1e-9)))

def get_rci_vectorized(df, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_func)

def send_discord(text):
    if not text.strip(): return
    try:
        for i in range(0, len(text), 1900):
            requests.post(DISCORD_URL, json={"content": text[i:i+1900]}, timeout=10)
            time.sleep(1)
    except Exception as e:
        print(f"Discord送信エラー: {e}", flush=True)

def get_ai_insight(msg_text):
    prompt = f"""あなたは日本株のプロトレーダーです。以下の「独自の条件」で仕分けされた銘柄群を分析してください。
    
    【仕分けの背景と条件】
    - デッドクロス(DC)をあえて「買い時」とする独自の逆張り戦略です。
    - 日足ベースの「25日VWAP（過去1ヶ月の出来高加重平均）」を算出し、現在価格がそれより上(📈上)なら需給良好、下(📉下)なら戻り売り警戒と判断しています。

    【必須項目】
    1. 各カテゴリの代表銘柄について、日足VWAPの需給関係を見た上で「だまし」か「本物」か解説。
    2. デイトレ・スイングでの具体的な買い時・売り時、目標価格の提示。
    
    【対象データ】
    {msg_text}
    """
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    try:
        res = requests.post(url, headers=headers, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
        data = res.json()
        if res.status_code == 200 and "candidates" in data:
            return data['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"AIエラー: {res.status_code}"
    except Exception as e: 
        return f"AI通信タイムアウト: {e}"

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。", flush=True)
        return

    print("🚀 日足VWAP搭載・完全仕分けスキャン開始...", flush=True)
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    categories = {
        "🟢【買い推奨】(RSI20以下 ＆ RCI-70以下)": [],
        "🔴【空売り推奨】(RSI90以上 ＆ RCI95以上)": [],
        "💀【同時DC】(メモ: 買い時)": [],
        "🦴【片方DC】(メモ: 翌日買い時)": [],
        "🚀【RSI10以下】(翌日急騰期待)": [],
        "⚠️【急落警戒】(RCI95以上 ＆ RSI80以上)": [],
        "✨【同時GC】(参考)": []
    }
    
    chunk_size = 200 
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        print(f"⏳ 分析中... {i} ～ {min(i+chunk_size, len(tickers))} 銘柄目", flush=True)
        try:
            # 日足VWAP計算のため、長めの期間(6ヶ月)を取得
            data = yf.download(chunk, period="6mo", interval="1d", progress=False, threads=False)
            close_df = data['Close'] if 'Close' in data else data
            vol_df = data['Volume'] if 'Volume' in data else None
            
            # 短期(9)と長期(14,26)
            rsi_s = get_rsi_vectorized(close_df, 9)
            rsi_l = get_rsi_vectorized(close_df, 14)
            rci_s = get_rci_vectorized(close_df, 9)
            rci_l = get_rci_vectorized(close_df, 26)
            
            # 💡 出来高×価格 の計算 (日足VWAP用)
            if vol_df is not None:
                cv_df = close_df * vol_df
            
            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    if len(c) < 30 or c.iloc[-1] < PRICE_MIN: continue
                    
                    if vol_df is not None:
                        v = vol_df[s].dropna()
                        if len(v) < 25 or v.tail(5).mean() < MIN_VOLUME_5D: continue
                    
                    p = c.iloc[-1]
                    c_rs, c_rl = rsi_s[s].iloc[-1], rsi_l[s].iloc[-1]
                    p_rs, p_rl = rsi_s[s].iloc[-2], rsi_l[s].iloc[-2]
                    
                    c_rcs, c_rcl = rci_s[s].iloc[-1], rci_l[s].iloc[-1]
                    p_rcs, p_rcl = rci_s[s].iloc[-2], rci_l[s].iloc[-2]
                    
                    # クロス判定
                    rsi_gc = (p_rs <= p_rl and c_rs > c_rl)
                    rsi_dc = (p_rs >= p_rl and c_rs < c_rl)
                    rci_gc = (p_rcs <= p_rcl and c_rcs > c_rcl)
                    rci_dc = (p_rcs >= p_rcl and c_rcs < c_rcl)
                    
                    sim_gc = rsi_gc and rci_gc
                    sim_dc = rsi_dc and rci_dc
                    single_dc = (rsi_dc or rci_dc) and not sim_dc
                    
                    cond_buy = (c_rs <= 20 and c_rcs <= -70)
                    cond_sell = (c_rs >= 90 and c_rcs >= 95)
                    cond_rsi10 = (c_rs <= 10)
                    cond_drop = (c_rcs >= 95 and c_rs >= 80)
                    
                    if cond_buy or cond_sell or cond_rsi10 or cond_drop or sim_gc or sim_dc or single_dc:
                        # 💡 日足ベースの「25日VWAP」を計算
                        cv_25d_sum = cv_df[s].tail(25).sum()
                        v_25d_sum = vol_df[s].tail(25).sum()
                        vwap_25d = cv_25d_sum / v_25d_sum if v_25d_sum > 0 else 0
                        
                        v_mark = "📈上" if p >= vwap_25d else "📉下"
                        
                        info = f"・{name_map[s]} ({s})\n  ⇒ 価格:{p:,.0f}円 (日足VWAP:{vwap_25d:,.0f} / {v_mark}) | RSI:{c_rs:.0f}/RCI:{c_rcs:.0f}"
                        
                        if cond_buy: categories["🟢【買い推奨】(RSI20以下 ＆ RCI-70以下)"].append(info)
                        if cond_sell: categories["🔴【空売り推奨】(RSI90以上 ＆ RCI95以上)"].append(info)
                        if sim_dc: categories["💀【同時DC】(メモ: 買い時)"].append(info)
                        if single_dc: categories["🦴【片方DC】(メモ: 翌日買い時)"].append(info)
                        if cond_rsi10: categories["🚀【RSI10以下】(翌日急騰期待)"].append(info)
                        if cond_drop: categories["⚠️【急落警戒】(RCI95以上 ＆ RSI80以上)"].append(info)
                        if sim_gc: categories["✨【同時GC】(参考)"].append(info)
                        
                except: continue
        except: continue
        time.sleep(1)

    print("✨ スキャン完了！", flush=True)

    has_hits = False
    ai_target_text = ""
    
    for cat_name, items in categories.items():
        if items:
            has_hits = True
            msg = f"**{cat_name}**\n" + "\n".join(items)
            send_discord(msg)
            # AIには各カテゴリ上位3件のみ渡す
            ai_target_text += f"{cat_name}\n" + "\n".join(items[:3]) + "\n\n"

    if has_hits:
        print("🤖 AIへ分析を依頼中...", flush=True)
        ai_msg = get_ai_insight(ai_target_text)
        send_discord(f"🤖 **【AI 攻略予報】**\n\n{ai_msg}")
        print("✅ 全ての処理が完了しました。", flush=True)
    else:
        print("🔍 該当銘柄なし", flush=True)
        send_discord("🔍 **【Jack株AI】**\n本日は該当する銘柄はありませんでした。")

if __name__ == "__main__":
    main()
