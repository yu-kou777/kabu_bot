import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime
import numpy as np

# --- 設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
# プライム市場全銘柄リスト（約1600件を想定）
# 本来は外部ファイルから読み込みますが、ここでは構造を示します
from prime_tickers import PRIME_TICKERS 

st.set_page_config(page_title="Jack株AI：リアルタイム全件検索", layout="wide")

# セッション状態の保持
if 'found_hits' not in st.session_state: st.session_state.found_hits = []
if 'reasons' not in st.session_state: st.session_state.reasons = {}

def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- UI ---
st.title("🔍 プライム全件：リアルタイム・スキャナー")
st.caption("全1,600銘柄を4つのバッチに分けて検索します。見つかった銘柄から順に表示されます。")

thr = st.slider("しきい値(RSI)", 10, 80, 35)

# 検索中表示用のエリアを確保
status_area = st.empty()
progress_bar = st.empty()
hits_area = st.empty()

if st.button("🚀 スキャン開始（バックグラウンド風・逐次表示）", use_container_width=True):
    st.session_state.found_hits = [] # リセット
    all_tickers = PRIME_TICKERS
    n = len(all_tickers)
    chunk_size = n // 4
    
    for batch_idx in range(4):
        # 4分割の範囲指定
        start = batch_idx * chunk_size
        end = (batch_idx + 1) * chunk_size if batch_idx != 3 else n
        chunk = all_tickers[start:end]
        
        status_area.info(f"📡 バッチ {batch_idx + 1}/4 を検索中... ({start} ～ {end} 銘柄目)")
        progress_bar.progress((batch_idx + 1) / 4)
        
        try:
            # バッチごとに一括ダウンロード
            data = yf.download(chunk, period="3mo", progress=False)['Close']
            
            for ticker in chunk:
                try:
                    # 個別銘柄のチェック
                    close = data[ticker].dropna()
                    if len(close) < 15: continue
                    rsi = calculate_rsi(close).tail(5).min()
                    
                    if rsi <= thr:
                        st.session_state.found_hits.append(ticker)
                        st.session_state.reasons[ticker] = f"RSI:{rsi:.1f}"
                        
                        # ✅ 見つかるたびに表示を更新（バックグラウンドで動いているように見せる）
                        with hits_area.container():
                            st.write(f"✅ **ヒット累計: {len(st.session_state.found_hits)} 銘柄**")
                            st.write(", ".join(st.session_state.found_hits))
                except: continue
        except Exception as e:
            st.error(f"バッチ {batch_idx+1} で通信エラーが発生しました。")
            
    status_area.success(f"🏁 スキャン完了！合計 {len(st.session_state.found_hits)} 銘柄見つかりました。")

# 保存セクション
if st.session_state.found_hits:
    st.write("---")
    selected = st.multiselect("監視リストに追加する銘柄を選択", PRIME_TICKERS, default=st.session_state.found_hits)
    
    if st.button("💾 選択した銘柄で監視を開始", type="primary"):
        final_data = []
        for t in selected:
            final_data.append({
                "ticker": t,
                "name": "プライム銘柄", # monitor.py側で和名取得
                "reason": st.session_state.reasons.get(t, "手動検索"),
                "at": datetime.now().strftime('%m/%d %H:%M')
            })
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        st.success("✅ 監視リストを保存しました！monitor.pyによる5分おき予測を開始します。")
