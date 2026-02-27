import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np

# --- 基本設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
AUTO_LIST_FILE = "auto_scan_list.json" # AI自動追加用
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船走井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：全機能復活版", layout="wide")

# セッション状態の初期化（検索結果を定着させるため）
if 'hits_5d' not in st.session_state: st.session_state.hits_5d = []
if 'hits_comp' not in st.session_state: st.session_state.hits_comp = []
if 'reasons' not in st.session_state: st.session_state.reasons = {}

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

def save_manual_list(selected_full_names):
    final_data = []
    for full in selected_full_names:
        code = full.split(" ")[0]
        final_data.append({
            "ticker": code,
            "name": JPX400_DICT.get(code, ""),
            "reason": st.session_state.reasons.get(code, "手動登録"),
            "at": get_jst_now().strftime('%m/%d %H:%M')
        })
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    st.success(f"✅ {len(final_data)} 銘柄を手動監視リストに保存しました！")

# --- UI：4タブ構成 ---
tab1, tab2, tab3, tab4 = st.tabs(["🔍 5日RSI検索", "📊 複合狙い撃ち", "🤖 15時自動検知", "☀️ 全状況確認"])
options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 直近5日間のRSI底打ち検知")
    thr1 = st.slider("しきい値(RSI)", 10, 85, 75, key="s1")
    if st.button("🚀 RSIスキャン開始", key="b1", use_container_width=True):
        st.session_state.hits_5d = []
        bar = st.progress(0); status = st.empty()
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar.progress((i+1)/len(JPX400_DICT))
            status.text(f"分析中: {t}")
            try:
                df = yf.download(t, period="3mo", progress=False)
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                rsi = calculate_rsi(close.dropna()).tail(5).min()
                if rsi <= thr1:
                    st.session_state.hits_5d.append(f"{t} {n}")
                    st.session_state.reasons[t] = f"5日RSI低迷({rsi:.1f})"
            except: continue
        status.empty(); bar.empty()
        st.rerun()
    
    sel1 = st.multiselect("監視に登録", options, default=st.session_state.hits_5d, key="ms1")
    if st.button("💾 手動リストを保存", key="sv1", use_container_width=True):
        save_manual_list(sel1)

with tab2:
    st.header("📊 RSI×RCI 複合検索（日足大底）")
    st.caption("条件：RSI <= 35 かつ RCI <= -80")
    if st.button("🔍 複合スキャン実行", key="b2", use_container_width=True):
        st.session_state.hits_comp = []
        bar2 = st.progress(0); status2 = st.empty()
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar2.progress((i+1)/len(JPX400_DICT))
            status2.text(f"分析中: {t}")
            try:
                df = yf.download(t, period="4mo", progress=False)
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                close_d = close.dropna()
                rv, rcv = calculate_rsi(close_d).iloc[-1], calculate_rci(close_d).iloc[-1]
                if (rv <= 35 and rcv <= -80) or (rv >= 75 and rcv >= 80):
                    st.session_state.hits_comp.append(f"{t} {n}")
                    st.session_state.reasons[t] = f"複合(RSI:{rv:.1f}, RCI:{rcv:.1f})"
            except: continue
        status2.empty(); bar2.empty()
        st.rerun()
    
    sel2 = st.multiselect("監視に登録(複合)", options, default=st.session_state.hits_comp, key="ms2")
    if st.button("💾 手動リストを保存(複合結果)", key="sv2", use_container_width=True):
        save_manual_list(sel2)

with tab3:
    st.header("🤖 15:00 AI自動検知（日足 狙い撃ち）")
    if os.path.exists(AUTO_LIST_FILE):
        with open(AUTO_LIST_FILE, 'r', encoding='utf-8') as f:
            auto_data = json.load(f)
        if auto_data:
            st.success(f"本日 15:00 検知：{len(auto_data)} 銘柄")
            for item in auto_data:
                st.write(f"✅ **{item['ticker']} {item['name']}**")
                st.caption(f"理由: {item['reason']} / 検知: {item['at']}")
                st.write("---")
        else: st.info("現在、自動検知銘柄はありません。")
    else: st.info("15時の自動実行後に表示されます。")

with tab4:
    st.header("☀️ 全監視状況（1分足監視対象）")
    colA, colB = st.columns(2)
    with colA:
        st.subheader("【手動登録】")
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                for i in json.load(f): st.write(f"🔹 {i['ticker']} {i['name']}")
    with colB:
        st.subheader("【15時自動】")
        if os.path.exists(AUTO_LIST_FILE):
            with open(AUTO_LIST_FILE, 'r', encoding='utf-8') as f:
                for i in json.load(f): st.write(f"🤖 {i['ticker']} {i['name']}")
