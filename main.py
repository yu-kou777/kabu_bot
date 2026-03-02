import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np

# --- 設定 ---
WATCHLIST_FILE = "jack_watchlist.json"

# プライム1000件相当のリスト（ここでは主要コードを例示。実際はここに1000件まで追加可能）
# ※コード量節約のため主要銘柄を記載。運用時に順次追加してください。
PRIME_1000 = ["1605.T","1801.T","1802.T","1925.T","2502.T","2802.T","2914.T","3382.T","4063.T","4502.T","4503.T","4519.T","4568.T","4901.T","5401.T","5713.T","6098.T","6301.T","6367.T","6501.T","6758.T","6857.T","6902.T","6920.T","6954.T","6981.T","7203.T","7267.T","7269.T","7741.T","7974.T","8001.T","8031.T","8035.T","8058.T","8306.T","8316.T","8411.T","8766.T","8801.T","9020.T","9101.T","9104.T","9432.T","9433.T","9983.T","9984.T"]
# (実際にはここから1000件まで自動生成、またはリスト読み込み可能です)

st.set_page_config(page_title="Jack株AI：プライム1000検索", layout="wide")

if 'ms_prime' not in st.session_state: st.session_state.ms_prime = []

def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- UI ---
st.title("🔍 プライム1,000銘柄・高速スキャナー")

thr = st.slider("しきい値(RSI)", 10, 80, 35)

if st.button("🚀 1,000件規模スキャン開始", use_container_width=True):
    hits = []
    bar = st.progress(0)
    status = st.empty()
    
    # 100件ずつ分割してスキャン（フリーズ防止）
    chunk_size = 100
    for i in range(0, len(PRIME_1000), chunk_size):
        chunk = PRIME_1000[i:i + chunk_size]
        status.text(f"📡 銘柄取得中... ({i} / {len(PRIME_1000)})")
        try:
            data = yf.download(chunk, period="3mo", progress=False)['Close']
            for ticker in chunk:
                close = data[ticker].dropna()
                if len(close) < 15: continue
                rsi = calculate_rsi(close).tail(5).min()
                if rsi <= thr:
                    hits.append(ticker)
        except: continue
        bar.progress(min((i + chunk_size) / len(PRIME_1000), 1.0))
    
    st.session_state.ms_prime = hits
    status.text("✅ スキャン完了！")
    st.rerun()

sel = st.multiselect("監視リストに保存", PRIME_1000, default=st.session_state.ms_prime)

if st.button("💾 監視リストを確定保存", type="primary", use_container_width=True):
    final = [{"ticker": t, "at": datetime.now().strftime('%H:%M')} for t in sel]
    with open(WATCHLIST_FILE, 'w') as f: json.dump(final, f)
    st.success("✅ 監視を開始しました。")
