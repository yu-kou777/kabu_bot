import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np

# --- 設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：究極統合パネル", layout="wide")

# メモリ（セッション）の初期化
if 'hits_tab1' not in st.session_state: st.session_state.hits_tab1 = []
if 'hits_tab2' not in st.session_state: st.session_state.hits_tab2 = []
if 'reasons' not in st.session_state: st.session_state.reasons = {}

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# --- 指標計算 ---
def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

def calculate_rci(series, period=9):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

def save_to_file(selected_names):
    data = []
    for full in selected_names:
        code = full.split(" ")[0]
        data.append({
            "ticker": code,
            "name": JPX400_DICT.get(code, ""),
            "reason": st.session_state.reasons.get(code, "手動登録"),
            "at": get_jst_now().strftime('%m/%d %H:%M')
        })
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    st.success(f"✅ {len(data)} 銘柄を監視リストに保存しました！")

# --- UI：3タブ構成 ---
tab1, tab2, tab3 = st.tabs(["🔍 5日RSI検索", "📊 RCI×RSI複合分析", "☀️ 監視リスト管理"])
options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 直近5日間のRSI低迷を探す")
    thr1 = st.slider("RSIしきい値", 10, 80, 60, key="slider_tab1")
    if st.button("🚀 RSIスキャン開始", key="btn_tab1"):
        st.session_state.hits_tab1 = []
        bar1 = st.progress(0); status1 = st.empty()
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar1.progress((i+1)/len(JPX400_DICT))
            status1.text(f"分析中: {t}")
            try:
                df = yf.download(t, period="3mo", progress=False)
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                rsi_s = calculate_rsi(close.dropna())
                min_rsi = rsi_s.tail(5).min()
                if min_rsi <= thr1:
                    name_full = f"{t} {n}"
                    st.session_state.hits_tab1.append(name_full)
                    st.session_state.reasons[t] = f"5日RSI低迷({min_rsi:.1f})"
            except: continue
        status1.empty(); bar1.empty()
        st.rerun()
    
    sel1 = st.multiselect("監視に追加（タブ1）", options, default=st.session_state.hits_tab1, key="m1")
    if st.button("💾 保存（タブ1）", key="save_tab1"):
        save_to_file(sel1)

with tab2:
    st.header("📊 RCI × RSI 複合分析（大底・天井）")
    st.write("RSI低迷 × RCI大底（売られすぎ）または RSI高騰 × RCI天井（買われすぎ）を検知します。")
    if st.button("🔍 複合スキャン実行", key="btn_tab2"):
        st.session_state.hits_tab2 = []
        bar2 = st.progress(0); status2 = st.empty()
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar2.progress((i+1)/len(JPX400_DICT))
            status2.text(f"分析中: {t}")
            try:
                df = yf.download(t, period="4mo", progress=False)
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                close_d = close.dropna()
                rsi_val = calculate_rsi(close_d).iloc[-1]
                rci_val = calculate_rci(close_d).iloc[-1]
                
                # 複合判定ロジック
                # 売られすぎ（大底）: RSI <= 35 かつ RCI <= -80
                if rsi_val <= 35 and rci_val <= -80:
                    name_full = f"{t} {n}"
                    st.session_state.hits_tab2.append(name_full)
                    st.session_state.reasons[t] = f"複合大底(RSI:{rsi_val:.1f}, RCI:{rci_val:.1f})"
                # 買われすぎ（天井）: RSI >= 75 かつ RCI >= 80
                elif rsi_val >= 75 and rci_val >= 80:
                    name_full = f"{t} {n}"
                    st.session_state.hits_tab2.append(name_full)
                    st.session_state.reasons[t] = f"複合天井(RSI:{rsi_val:.1f}, RCI:{rci_val:.1f})"
            except: continue
        status2.empty(); bar2.empty()
        st.rerun()
    
    sel2 = st.multiselect("監視に追加（タブ2）", options, default=st.session_state.hits_tab2, key="m2")
    if st.button("💾 保存（タブ2）", key="save_tab2"):
        save_to_file(sel2)

with tab3:
    st.header("☀️ 現在の監視リスト")
    if st.button("🗑️ リストを空にする", type="primary"):
        save_to_file([]); st.rerun()
    
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            watch_data = json.load(f)
            for item in watch_data:
                st.write(f"🔹 **{item['ticker']} {item.get('name')}**")
                st.caption(f"理由: {item.get('reason')} / 登録: {item.get('at')}")
                st.write("---")
