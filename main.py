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

st.set_page_config(page_title="Jack株AI：完全版", layout="wide")

# メモリの初期化
if 'reasons' not in st.session_state: st.session_state.reasons = {}
# multiselectの値を保持するためのキーを初期化
if 'm1_val' not in st.session_state: st.session_state.m1_val = []
if 'm2_val' not in st.session_state: st.session_state.m2_val = []

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

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

def save_and_report(selected_names):
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
    st.success(f"✅ {len(data)} 銘柄を保存しました！")

# --- UI ---
tab1, tab2, tab3 = st.tabs(["🌙 5日RSI検索", "📊 RCI複合分析", "☀️ 監視リスト管理"])
all_options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 直近5日間のRSI低迷を探す")
    thr = st.slider("RSIしきい値", 10, 85, 70, key="slider1")
    if st.button("🚀 スキャン開始", key="b1"):
        new_hits = []
        bar = st.progress(0); status = st.empty()
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar.progress((i+1)/len(JPX400_DICT))
            status.text(f"取得中: {t}")
            try:
                df = yf.download(t, period="3mo", progress=False)
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                rsi = calculate_rsi(close.dropna())
                val = rsi.tail(5).min()
                if val <= thr:
                    name_full = f"{t} {n}"
                    new_hits.append(name_full)
                    st.session_state.reasons[t] = f"5日RSI低迷({val:.1f})"
            except: continue
        # スキャン結果をメモリに直接流し込む
        st.session_state.m1_val = new_hits
        status.empty(); bar.empty()
        st.rerun()
    
    # 枠に結果が自動で入るように設定
    sel1 = st.multiselect("監視に追加", all_options, key="m1", default=st.session_state.m1_val)
    if st.button("💾 保存（タブ1）", key="sv1"):
        save_and_report(sel1)

with tab2:
    st.header("📊 RCI × RSI 複合分析")
    if st.button("🔍 複合スキャン開始", key="b2"):
        new_hits2 = []
        bar2 = st.progress(0); status2 = st.empty()
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar2.progress((i+1)/len(JPX400_DICT))
            status2.text(f"分析中: {t}")
            try:
                df = yf.download(t, period="4mo", progress=False)
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                rsi_v = calculate_rsi(close.dropna()).iloc[-1]
                rci_v = calculate_rci(close.dropna()).iloc[-1]
                if (rsi_v <= 35 and rci_v <= -80) or (rsi_v >= 75 and rci_v >= 80):
                    name_full = f"{t} {n}"
                    new_hits2.append(name_full)
                    st.session_state.reasons[t] = f"複合(RSI:{rsi_v:.1f}, RCI:{rci_v:.1f})"
            except: continue
        st.session_state.m2_val = new_hits2
        status2.empty(); bar2.empty()
        st.rerun()
    
    sel2 = st.multiselect("監視に追加", all_options, key="m2", default=st.session_state.m2_val)
    if st.button("💾 保存（タブ2）", key="sv2"):
        save_and_report(sel2)

with tab3:
    st.header("☀️ 現在の監視リスト")
    if st.button("🗑️ 全削除", type="primary", key="del"):
        st.session_state.m1_val = []; st.session_state.m2_val = []
        save_and_report([]); st.rerun()
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            for item in json.load(f):
                st.write(f"🔹 **{item['ticker']} {item.get('name')}**")
                st.caption(f"理由: {item.get('reason')} / 登録: {item.get('at')}")
