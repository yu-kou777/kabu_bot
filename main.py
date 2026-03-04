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

# --- 📈 RSI計算 (指数平滑移動平均ベース) ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 📡 プライム市場スキャン実行関数 ---
def run_prime_scan(price_limit=3000):
    st.info("🚀 JPXからプライム市場の最新銘柄リストを取得中...")
    try:
        res = requests.get(JPX_LIST_URL, headers=HEADERS, timeout=30)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        # プライム市場のみ抽出
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        st.error(f"リスト取得失敗: {e}")
        return

    tickers = list(name_map.keys())
    hits = {}
    progress_bar = st.progress(0)
    status_text = st.empty()

    # 💡 100銘柄ずつのバッチで株価とRSIを一括チェック
    batch_size = 100
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_text.text(f"📊 分析中: {i} / {len(tickers)} 銘柄完了...")
        
        try:
            # 高速化のため期間を1ヶ月(1mo)に限定
            data = yf.download(batch, period="1mo", interval="1d", progress=False, threads=False)
            close_data = data['Close']
            
            for t in batch:
                try:
                    c = close_data[t].dropna() if isinstance(close_data, pd.DataFrame) else close_data.dropna()
                    if c.empty: continue
                    
                    # ✅ 株価3,000円以上の条件
                    current_price = float(c.iloc[-1])
                    if current_price < price_limit: continue
                    
                    # RSI計算
                    rsi = calculate_rsi(c, 14).iloc[-1]
                    
                    # RSI 30以下 または 70以上でお宝検知
                    if not np.isnan(rsi) and (rsi <= 30 or rsi >= 70):
                        status = "📉 底値圏" if rsi <= 30 else "📈 高値圏"
                        hits[t] = {
                            "name": name_map[t], 
                            "reason": f"{status}(Price:{current_price:,.0f}/RSI:{rsi:.0f})"
                        }
                except: continue
        except: pass
        
        progress_bar.progress(min((i + batch_size) / len(tickers), 1.0))
        time.sleep(2) # Yahooへのマナー

    # 結果を保存
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": time.strftime('%Y-%m-%d %H:%M'), "hits": hits}, f, ensure_ascii=False, indent=2)
    
    status_text.text("✨ スキャン完了！")
    st.balloons()
    return hits

# --- メイン画面構成 ---
st.title("📊 プライム市場 司令塔ダッシュボード")

# サイドバー設定
st.sidebar.header("🔍 スキャン設定")
price_min = st.sidebar.number_input("最小株価条件 (円)", value=3000, step=100)
if st.sidebar.button("🚀 プライム全体スキャンを開始"):
    run_prime_scan(price_min)

auto_refresh = st.sidebar.toggle("⏱️ 自動更新 (1分)", value=False)

# 監視リスト表示部分
if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if watchlist:
        st.subheader("📋 現在の監視銘柄")
        # （前回同様のリアルタイム表示ロジックをここに継続）
        # ... (省略) ...

st.divider()

# スキャン結果表示
st.header(f"✨ 条件合致銘柄 (プライム市場 / {price_min:,.0f}円以上)")
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.info(f"📅 最終スキャン完了時刻: {data.get('date', '不明')}")
    
    hits = data.get('hits', {})
    if not hits:
        st.write("現在、条件に合致するお宝銘柄は見つかりませんでした。")
    else:
        selected = []
        keys = list(hits.keys())
        # 3列グリッドで表示
        for i in range(0, len(keys), 3):
            cols = st.columns(3)
            for j in range(3):
                if i+j < len(keys):
                    t = keys[i+j]
                    info = hits[t]
                    with cols[j]:
                        if st.checkbox(f"**{info['name']}** ({t})\n{info['reason']}", key=f"sel_{t}"):
                            selected.append({"ticker": t, "name": info['name']})
        
        if st.button("💾 選択した銘柄を監視リストへ登録", type="primary", use_container_width=True):
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(selected, f, ensure_ascii=False, indent=2)
            st.success("監視リストを更新しました！")

if auto_refresh:
    time.sleep(60)
    st.rerun()
