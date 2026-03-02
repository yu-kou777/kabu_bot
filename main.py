import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np

# --- 設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
AUTO_LIST_FILE = "auto_scan_list.json"

# プライム市場全件（主要銘柄を網羅した1000〜1600件規模のリストを想定）
# ※リストが長すぎるため、ここでは代表的なコードを表示していますが、
# プログラム内部で全件を4分割して処理するロジックを実装しています。
from prime_tickers import PRIME_TICKERS # 別途全銘柄リストを用意するか、ここに記述

st.set_page_config(page_title="Jack株AI：プライム全件検索", layout="wide")

if 'ms_prime' not in st.session_state: st.session_state.ms_prime = []
if 'reasons' not in st.session_state: st.session_state.reasons = {}

def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

def save_manual_list(selected_list):
    final_data = []
    for ticker in selected_list:
        final_data.append({
            "ticker": ticker,
            "name": "プライム銘柄", # 和名はmonitor.pyで取得またはリストから参照
            "reason": st.session_state.reasons.get(ticker, "手動検索"),
            "at": datetime.now().strftime('%m/%d %H:%M')
        })
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    st.success(f"✅ {len(final_data)} 銘柄を保存しました。")

# --- UI ---
st.title("🔍 プライム市場：全件・4分割スキャナー")

thr = st.slider("しきい値(RSI)", 10, 80, 35)

if st.button("🚀 全件スキャン開始（4バッチ処理）", use_container_width=True):
    all_tickers = PRIME_TICKERS # 約1600銘柄
    hits = []
    
    # ✅ 4分割ロジック
    n = len(all_tickers)
    chunk_size = n // 4
    
    bar = st.progress(0)
    status = st.empty()
    
    for i in range(4):
        # 4つのバッチに分ける
        start = i * chunk_size
        end = (i + 1) * chunk_size if i != 3 else n
        chunk = all_tickers[start:end]
        
        status.info(f"⏳ バッチ {i+1}/4 を処理中... ({len(chunk)} 銘柄)")
        
        try:
            # 一括ダウンロード
            data = yf.download(chunk, period="3mo", progress=False)['Close']
            
            for ticker in chunk:
                try:
                    close = data[ticker].dropna()
                    if len(close) < 15: continue
                    rsi = calculate_rsi(close).tail(5).min()
                    if rsi <= thr:
                        hits.append(ticker)
                        st.session_state.reasons[ticker] = f"RSI:{rsi:.1f}"
                except: continue
        except:
            st.error(f"バッチ {i+1} でデータ取得エラーが発生しました。")
            
        bar.progress((i + 1) / 4)
    
    st.session_state.ms_prime = hits
    status.success(f"✅ スキャン完了！ {len(hits)} 銘柄が条件に合致しました。")
    st.rerun()

sel = st.multiselect("監視リストに保存", PRIME_TICKERS, default=st.session_state.ms_prime)

if st.button("💾 選択した銘柄で監視を開始", type="primary", use_container_width=True):
    save_manual_list(sel)
