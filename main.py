import streamlit as st
import json
import os
import yfinance as yf
import pandas as pd
import time
import io
import requests
import numpy as np

# --- ⚙️ 基本設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"
JPX_LIST_URL = "https://www.jpx.co.jp/markets/statistics-banner/quote/tvdivq0000001vg2-att/data_j.xls"
HEADERS = {"User-Agent": "Mozilla/5.0"}

st.set_page_config(page_title="Jack株AI：プライム司令塔", layout="wide")

# --- 📈 RSI計算 (Standard/Wilder Method) ---
# $$RSI = 100 - \frac{100}{1 + \frac{\text{Average Gain}}{\text{Average Loss}}}$$
def calculate_rsi(series, period=14):
    if len(series) < period: return pd.Series([np.nan] * len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 📡 プライム市場スキャン実行関数 ---
def run_prime_scan(price_limit):
    status_box = st.empty()
    status_box.info("🚀 JPXからプライム市場の最新銘柄リストを取得中...")
    
    try:
        res = requests.get(JPX_LIST_URL, headers=HEADERS, timeout=30)
        # engine='xlrd' を明示的に指定して.xlsを読み込む
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        st.error(f"❌ リスト取得失敗: {e}")
        return None

    tickers = list(name_map.keys())
    hits = {}
    progress_bar = st.progress(0)
    
    # 💡 50銘柄ずつのバッチで一括チェック（Yahooの制限対策）
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_box.text(f"📊 分析中: {i} / {len(tickers)} 銘柄完了... (現在ヒット: {len(hits)}件)")
        
        try:
            # 高速化のため期間を1ヶ月に限定
            data = yf.download(batch, period="1mo", interval="1d", progress=False, threads=False)
            close_data = data['Close']
            
            for t in batch:
                try:
                    c = close_data[t].dropna() if isinstance(close_data, pd.DataFrame) else close_data.dropna()
                    if c.empty: continue
                    
                    # ✅ 株価条件
                    current_price = float(c.iloc[-1])
                    if current_price < price_limit: continue
                    
                    # RSI計算
                    rsi_val = calculate_rsi(c, 14).iloc[-1]
                    
                    # RSI 30以下 または 70以上
                    if not np.isnan(rsi_val) and (rsi_val <= 30 or rsi_val >= 70):
                        hits[t] = {
                            "name": name_map[t], 
                            "price": current_price,
                            "rsi": round(rsi_val, 1)
                        }
                except: continue
        except: pass
        
        progress_bar.progress(min((i + batch_size) / len(tickers), 1.0))
        time.sleep(1) # Yahooへの負荷軽減

    # 結果をファイルに保存
    result_data = {"date": time.strftime('%Y-%m-%d %H:%M'), "hits": hits}
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    status_box.success(f"✨ スキャン完了！ {len(hits)}件の銘柄を検知しました。")
    st.balloons()
    return hits

# --- 🖥️ ダッシュボード画面 ---
st.title("📊 プライム市場 司令塔ダッシュボード")

# サイドバー設定
st.sidebar.header("🔍 スキャン設定")
price_min = st.sidebar.number_input("最小株価条件 (円)", value=3000, step=100)
if st.sidebar.button("🚀 スキャンを開始", use_container_width=True):
    run_prime_scan(price_min)

auto_refresh = st.sidebar.toggle("⏱️ 画面自動更新 (1分)", value=False)

# 監視中の銘柄（リアルタイム）
if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if watchlist:
        st.subheader("📋 現在の監視銘柄（リアルタイム状況）")
        rows = []
        for item in watchlist:
            try:
                # 1分足で最新取得
                d = yf.download(item['ticker'], period="1d", interval="1m", progress=False)
                c = d['Close'].iloc[:,0] if isinstance(d['Close'], pd.DataFrame) else d['Close']
                now_p = float(c.iloc[-1])
                now_rsi = calculate_rsi(c, 14).iloc[-1]
                rows.append([item['name'], item['ticker'], f"{now_p:,.1f}", f"{now_rsi:.1f}"])
            except: rows.append([item['name'], item['ticker'], "取得中", "-"])
        
        st.table(pd.DataFrame(rows, columns=["銘柄名", "コード", "現在価格", "RSI(1分)"]))

st.divider()

# スキャン結果
st.header(f"✨ 条件合致銘柄 ({price_min:,.0f}円以上)")
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        scan_results = json.load(f)
    
    st.info(f"📅 最終スキャン：{scan_results.get('date', '不明')}")
    hits = scan_results.get('hits', {})
    
    if not hits:
        st.write("現在、条件に合うお宝銘柄は見つかりませんでした。")
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
                        label = f"**{info['name']}** ({t})\n価格: {info['price']:,.0f}円 / RSI: {info['rsi']}"
                        if st.checkbox(label, key=f"sel_{t}"):
                            selected.append({"ticker": t, "name": info['name']})
        
        if st.button("💾 選択した銘柄を監視リストに保存", type="primary", use_container_width=True):
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(selected, f, ensure_ascii=False, indent=2)
            st.success("監視リストを更新しました。GitHub側で通知が開始されます！")

if auto_refresh:
    time.sleep(60)
    st.rerun()
