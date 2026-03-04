import streamlit as st
import json
import os
import yfinance as yf
import pandas as pd
import time

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI：ダッシュボード", layout="wide")

def calculate_rsi(series, period=14):
    delta = series.diff(); gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def fetch_status(ticker):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        c = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        rsi_val = calculate_rsi(c, 14).iloc[-1]
        now_p = float(c.iloc[-1])
        return [now_p, round(rsi_val, 1), "監視中"]
    except: return [0.0, 0.0, "待機中"]

# --- メイン表示 ---
st.title("📊 リアルタイム監視ダッシュボード")

# ✅ 自動更新ボタン
auto_refresh = st.sidebar.toggle("⏱️ 1分おきに自動更新", value=False)

if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if watchlist:
        rows = [[item['name'], item['ticker']] + fetch_status(item['ticker']) for item in watchlist]
        df = pd.DataFrame(rows, columns=["銘柄名", "コード", "現在値", "RSI", "状況"])
        st.dataframe(df.style.highlight_between(left=0, right=30, subset=['RSI'], color='#e1f5fe')
                           .highlight_between(left=70, right=100, subset=['RSI'], color='#ffebee'), 
                     use_container_width=True)

st.divider()

st.header("✨ お宝スキャン結果")
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.info(f"📅 最終更新: {data.get('date', '不明')}")
    hits = data.get('hits', {})
    
    selected = []
    keys = list(hits.keys())
    for i in range(0, len(keys), 3):
        cols = st.columns(3)
        for j in range(3):
            if i+j < len(keys):
                t = keys[i+j]
                info = hits[t]
                name = info.get('name', t) if isinstance(info, dict) else t
                if st.checkbox(f"**{name}** ({t})", key=f"sel_{t}"):
                    selected.append({"ticker": t, "name": name})
    
    if st.button("💾 監視を開始する", type="primary", use_container_width=True):
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(selected, f, ensure_ascii=False, indent=2)
        st.success("保存完了！")

# ✅ 自動更新ロジック
if auto_refresh:
    time.sleep(60)
    st.rerun()
