import streamlit as st
import json
import os
import yfinance as yf
import pandas as pd
import time
import numpy as np
from datetime import datetime

# --- ⚙️ 設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI：司令塔", layout="wide")

# --- 📈 テクニカル指標（RSI）の計算 ---
def calculate_rsi(series, period=14):
    if len(series) < period: return pd.Series([np.nan] * len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 📋 プライム市場 主要銘柄リスト (3000円以上の候補を網羅) ---
def get_prime_database():
    # 💡 プライム市場の時価総額上位 & 高価格帯中心のリスト
    return {
        "8035.T": "東エレク", "9984.T": "SBG", "6758.T": "ソニーG", "7203.T": "トヨタ", 
        "6857.T": "アドバンテ", "6723.T": "ルネサス", "6146.T": "ディスコ", "6954.T": "ファナック",
        "4063.T": "信越化", "6367.T": "ダイキン", "6273.T": "SMC", "7974.T": "任天堂",
        "4519.T": "中外薬", "4502.T": "武田", "8001.T": "伊藤忠", "8058.T": "三菱商",
        "8306.T": "三菱UFJ", "8316.T": "三井住友", "9020.T": "JR東日本", "9022.T": "JR東海",
        "9201.T": "JAL", "9202.T": "ANA", "2502.T": "アサヒ", "2802.T": "味の素",
        "1925.T": "大和ハウス", "1928.T": "積水ハウス", "5108.T": "ブリヂストン", "5401.T": "日本製鉄",
        "6301.T": "コマツ", "6501.T": "日立", "6503.T": "三菱電", "6645.T": "オムロン",
        "6701.T": "NEC", "6702.T": "富士通", "6902.T": "デンソー", "6920.T": "レーザーテク",
        "6981.T": "村田製", "7267.T": "ホンダ", "7733.T": "オリンパス", "7741.T": "HOYA",
        "8031.T": "三井物産", "8766.T": "東京海上", "8801.T": "三井不動", "8802.T": "三菱地所",
        "9101.T": "日本郵船", "9613.T": "NTTデータ", "9983.T": "ファストリ", "4901.T": "富士フイルム",
        "4452.T": "花王", "4503.T": "アステラス", "6098.T": "リクルート", "4661.T": "オリエンタルランド",
        "3382.T": "7&i", "6201.T": "豊田織機", "9104.T": "商船三井", "9107.T": "川崎汽",
        "4911.T": "資生堂", "6326.T": "クボタ", "6506.T": "安川電", "8113.T": "ユニチャーム",
        "8267.T": "イオン", "8604.T": "野村HD", "9501.T": "東電HD", "9502.T": "中部電",
        "9503.T": "関西電", "4689.T": "LINEヤフー", "2413.T": "エムスリー", "3064.T": "モノタロウ"
        # 💡 ここに順次追加することでプライム全体をカバー
    }

# --- 📡 スキャン実行 ---
def run_enhanced_scan(price_limit):
    status_box = st.empty()
    status_box.info("🚀 プライム市場を3,000円基準でスキャン中...")
    
    name_map = get_prime_database()
    tickers = list(name_map.keys())
    hits = {}
    progress_bar = st.progress(0)
    
    batch_size = 20
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_box.text(f"📊 分析進捗: {i} / {len(tickers)} 銘柄 (検知: {len(hits)}件)")
        
        try:
            data = yf.download(batch, period="1mo", interval="1d", progress=False, threads=False)
            close_data = data['Close'] if 'Close' in data else data
            
            for t in batch:
                try:
                    c = close_data[t].dropna() if isinstance(close_data, pd.DataFrame) else close_data.dropna()
                    if c.empty: continue
                    
                    price = float(c.iloc[-1])
                    if price < price_limit: continue # 3000円フィルタ
                    
                    rsi_val = calculate_rsi(c, 14).iloc[-1]
                    
                    # 判定基準
                    if not np.isnan(rsi_val) and (rsi_val <= 30 or rsi_val >= 70):
                        hits[t] = {
                            "name": name_map[t], 
                            "price": price,
                            "rsi": round(rsi_val, 1)
                        }
                except: continue
        except: pass
        
        progress_bar.progress(min((i + batch_size) / len(tickers), 1.0))
        time.sleep(1)

    result_data = {"date": datetime.now().strftime('%Y-%m-%d %H:%M'), "hits": hits}
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    status_box.success(f"✨ スキャン完了！ {len(hits)}件のお宝候補が見つかりました。")
    st.balloons()
    return hits

# --- 🖥️ ダッシュボード表示 ---
st.title("📊 プライム司令塔ダッシュボード")

# サイドバー
st.sidebar.header("🔍 フィルタ設定")
price_min = st.sidebar.number_input("最小株価条件 (円)", value=3000, step=500)
if st.sidebar.button("🚀 最新スキャンを開始"):
    run_enhanced_scan(price_min)

auto_refresh = st.sidebar.toggle("⏱️ 画面自動更新 (1分)", value=False)

# 監視リスト
if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if watchlist:
        st.subheader("📋 現在の監視リスト（リアルタイム）")
        rows = []
        for item in watchlist:
            try:
                d = yf.download(item['ticker'], period="1d", interval="1m", progress=False)
                c = d['Close'].iloc[:,0] if isinstance(d['Close'], pd.DataFrame) else d['Close']
                now_p = float(c.iloc[-1])
                now_rsi = calculate_rsi(c, 14).iloc[-1]
                rows.append([item['name'], item['ticker'], f"{now_p:,.1f}", f"{now_rsi:.1f}"])
            except: rows.append([item['name'], item['ticker'], "取得中", "-"])
        st.table(pd.DataFrame(rows, columns=["銘柄名", "コード", "最新価格", "RSI(1分)"]))

st.divider()

# スキャン結果
st.header(f"✨ 条件合致銘柄 ({price_min:,.0f}円以上)")
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        scan_results = json.load(f)
    
    st.caption(f"📅 最終スキャン：{scan_results.get('date', '不明')}")
    hits = scan_results.get('hits', {})
    
    if not hits:
        st.write("現在、条件に合うお宝銘柄はありません。スキャンを実行してください。")
    else:
        selected = []
        keys = list(hits.keys())
        for i in range(0, len(keys), 3):
            cols = st.columns(3)
            for j in range(3):
                if i+j < len(keys):
                    t = keys[i+j]
                    info = hits[t]
                    with cols[j]:
                        icon = "🟥" if info['rsi'] >= 70 else "🟦"
                        label = f"{icon} **{info['name']}** ({t})\n価格: {info['price']:,.0f}円 / RSI: {info['rsi']}"
                        if st.checkbox(label, key=f"sel_{t}"):
                            selected.append({"ticker": t, "name": info['name']})
        
        if st.button("💾 選択した銘柄で監視を開始する", type="primary", use_container_width=True):
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(selected, f, ensure_ascii=False, indent=2)
            st.success("監視リストを更新しました！")

if auto_refresh:
    time.sleep(60)
    st.rerun()
