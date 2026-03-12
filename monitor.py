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
        return {"8035.T": "東エレク(プ)", "9984.T": "SBG(プ)", "7203.T": "トヨタ(プ)", "8306.T": "三菱UFJ(プ)"}

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
    prompt = f"""あなたは日本株のプロトレーダーです。以下の厳選された銘柄群を分析してください。
    
    【重要：分析の評価基準】
    - VWAP乖離率：25日VWAPから下に大きくマイナス乖離しているほど「反発（リバウンド）のエネルギーが強い」と評価し、プラスに乖離している銘柄（急落警戒カテゴリ）は「下落の危険が高い」と評価してください。
    - トレンド(MA25,60,200)：[🚀完全上昇(PO)]の中での買いシグナルは本物、[📉完全下降(PO)]の中での買いシグナルは「だましの可能性あり」として厳しく判定してください。

    【必須項目】
    1. 各銘柄のVWAP乖離とトレンドを踏まえた「だまし回避」の具体的な解説。
    2. デイトレ・スイングでの買い時/売り時のタイミング、反発・急落の予想日、目標価格。
    
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

    print("🚀 VWAP乖離＆トレンド搭載・完全仕分けスキャン開始...", flush=True)
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    # カテゴリごとに (乖離率, テキスト) のタプルで保存（後でソートして絞り込むため）
    categories = {
        "🔴【空売り推奨】(RSI90以上 ＆ RCI95以上)": [],
        "🟢【買い推奨】(RSI20以下 ＆ RCI-70以下)": [],
        "✨【同時GC】(RSI50以下/RCI-50以下)": [],
        "🦴【片方GC】(翌日買い時)": [],
        "🚀【RSI10以下】(翌日急騰期待)": []
    }
    
    chunk_size = 200 
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        print(f"⏳ 分析中... {i} ～ {min(i+chunk_size, len(tickers))} 銘柄目", flush=True)
        try:
            # 💡 MA200を計算するため、1年分のデータを取得
            data = yf.download(chunk, period="1y", interval="1d", progress=False, threads=False)
            close_df = data['Close'] if 'Close' in data else data
            vol_df = data['Volume'] if 'Volume' in data else None
            
            rsi_s = get_rsi_vectorized(close_df, 9)
            rsi_l = get_rsi_vectorized(close_df, 14)
            rci_s = get_rci_vectorized(close_df, 9)
            rci_l = get_rci_vectorized(close_df, 26)
            
            if vol_df is not None:
                cv_df = close_df * vol_df
            
            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    # 200日線を出したいので最低200日のデータが必要
                    if len(c) < 200 or c.iloc[-1] < PRICE_MIN: continue
                    
                    if vol_df is not None:
                        v = vol_df[s].dropna()
                        if len(v) < 25 or v.tail(5).mean() < MIN_VOLUME_5D: continue
                    
                    p = c.iloc[-1]
                    
                    # MA計算
                    ma25 = c.rolling(25).mean().iloc[-1]
                    ma60 = c.rolling(60).mean().iloc[-1]
                    ma200 = c.rolling(200).mean().iloc[-1]
                    
                    # 💡 トレンド判定 (パーフェクトオーダー)
                    trend_mark = "〰️混迷"
                    if p > ma25 and ma25 > ma60 and ma60 > ma200:
                        trend_mark = "🚀完全上昇(PO)"
                    elif p < ma25 and ma25 < ma60 and ma60 < ma200:
                        trend_mark = "📉完全下降(PO)"
                    elif ma25 > ma60:
                        trend_mark = "↗️短期上昇"
                    elif ma25 < ma60:
                        trend_mark = "↘️短期下降"

                    c_rs, c_rl = rsi_s[s].iloc[-1], rsi_l[s].iloc[-1]
                    p_rs, p_rl = rsi_s[s].iloc[-2], rsi_l[s].iloc[-2]
                    
                    c_rcs, c_rcl = rci_s[s].iloc[-1], rci_l[s].iloc[-1]
                    p_rcs, p_rcl = rci_s[s].iloc[-2], rci_l[s].iloc[-2]
                    
                    # クロス判定 (GC)
                    rsi_gc = (p_rs <= p_rl and c_rs > c_rl)
                    rci_gc = (p_rcs <= p_rcl and c_rcs > c_rcl)
                    
                    sim_gc = rsi_gc and rci_gc
                    single_gc = (rsi_gc or rci_gc) and not sim_gc
                    
                    # 条件
                    cond_sell = (c_rs >= 90 and c_rcs >= 95)
                    cond_buy = (c_rs <= 20 and c_rcs <= -70)
                    cond_sim_gc = (sim_gc and c_rs <= 50 and c_rcs <= -50)
                    cond_single_gc = (single_gc and c_rs <= 50 and c_rcs <= -50)
                    cond_rsi10 = (c_rs <= 10)
                    
                    if any([cond_sell, cond_buy, cond_sim_gc, cond_single_gc, cond_rsi10]):
                        # 💡 25日VWAPと乖離率の計算
                        cv_25d_sum = cv_df[s].tail(25).sum()
                        v_25d_sum = vol_df[s].tail(25).sum()
                        vwap_25d = cv_25d_sum / v_25d_sum if v_25d_sum > 0 else p
                        
                        # 乖離率(%)
                        kairi = ((p - vwap_25d) / vwap_25d) * 100
                        kairi_str = f"{kairi:+.1f}%"
                        
                        info = f"・{name_map[s]} ({s}) {p:,.0f}円\n   ⇒ VWAP乖離: [{kairi_str}] | RSI:{c_rs:.0f}/RCI:{c_rcs:.0f} | 状態: {trend_mark}"
                        
                        # 乖離率と一緒に保存
                        if cond_sell: categories["🔴【空売り推奨】(RSI90以上 ＆ RCI95以上)"].append((kairi, info))
                        if cond_buy: categories["🟢【買い推奨】(RSI20以下 ＆ RCI-70以下)"].append((kairi, info))
                        if cond_sim_gc: categories["✨【同時GC】(RSI50以下/RCI-50以下)"].append((kairi, info))
                        if cond_single_gc: categories["🦴【片方GC】(翌日買い時)"].append((kairi, info))
                        if cond_rsi10: categories["🚀【RSI10以下】(翌日急騰期待)"].append((kairi, info))
                        
                except: continue
        except: continue
        time.sleep(1)

    print("✨ スキャン完了！", flush=True)

    has_hits = False
    ai_target_text = ""
    
    for cat_name, items in categories.items():
        if items:
            has_hits = True
            
            # 💡 絞り込みロジック：乖離率でソートして上位5件を厳選
            if "空売り" in cat_name:
                # 空売りは「上に乖離している（プラスが大きい）」ものを優先
                sorted_items = sorted(items, key=lambda x: x[0], reverse=True)[:5]
            else:
                # 買いは「下に乖離している（マイナスが大きい）」ものを優先（売られすぎ反発狙い）
                sorted_items = sorted(items, key=lambda x: x[0])[:5]
                
            # テキストだけを取り出す
            text_list = [item[1] for item in sorted_items]
            
            msg = f"**{cat_name}**\n" + "\n".join(text_list)
            send_discord(msg)
            
            # AIには各カテゴリ上位2件だけ渡してパンクを防ぐ
            ai_target_text += f"{cat_name}\n" + "\n".join(text_list[:2]) + "\n\n"

    if has_hits:
        print("🤖 AIへ分析を依頼中...", flush=True)
        ai_msg = get_ai_insight(ai_target_text)
        send_discord(f"🤖 **【AI 反発予想 ＆ だまし回避】**\n\n{ai_msg}")
        print("✅ 全ての処理が完了しました。", flush=True)
    else:
        print("🔍 該当銘柄なし", flush=True)
        send_discord("🔍 **【Jack株AI】**\n本日はメモの条件に合致する銘柄はありませんでした。")

if __name__ == "__main__":
    main()
