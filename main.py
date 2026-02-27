import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np
import time

# --- 基本設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
# JPX400から主要な銘柄を抜粋（400銘柄全件に増やすことも可能です）
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：検索強化版", layout="wide")

# セッション管理
if 'reasons' not in st.session_state: st.session_state.reasons = {}
if 'hits_1' not in st.session_state: st.session_state.hits_1 = []
if 'hits_2' not in st.session_state: st.session_state.hits_2 = []

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# 手動計算RSI
def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

# 手動計算RCI
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
        reason = st.session_state.reasons.get(code, "手動登録")
        data.append({"ticker": code, "name": JPX400_DICT.get(code, ""), "reason": reason, "at": get_jst_now().strftime('%m/%d %H:%M')})
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    st.success(f"✅ {len(data)} 銘柄を監視リストに保存しました！")

# --- UI ---
tab1, tab2, tab3 = st.tabs(["🌙 5日RSI検索", "📊 RCI複合分析", "☀️ 監視リスト管理"])
options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 直近5日間のRSIで探す")
    st.write("直近5日間の日足データのうち、一度でもしきい値を下回った銘柄を抽出します。")
    thr = st.slider("RSIしきい値", 10, 80, 55, key="slider_tab1")
    
    if st.button("🚀 RSIスキャン開始", key="btn_tab1"):
        st.session_state.hits_1 = []
        bar = st.progress(0); msg = st.empty()
        tickers = list(JPX400_DICT.keys())
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers))
            msg.text(f"分析中: {t} {JPX400_DICT[t]}")
            try:
                # 1銘柄ずつ確実に最新データを取得
                df = yf.download(t, period="3mo", interval="1d", progress=False)
                if df.empty: continue
                
                # yfinanceの構造変更（マルチインデックス等）に左右されないデータ抽出
                close_s = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                close_s = close_s.dropna()
                
                rsi_s = calculate_rsi(close_s)
                min_5d_rsi = rsi_s.tail(5).min()
                
                if min_5d_rsi <= thr:
                    name_full = f"{t} {JPX400_DICT[t]}"
                    st.session_state.hits_1.append(name_full)
                    st.session_state.reasons[t] = f"5日RSI低迷({min_5d_rsi:.1f})"
            except Exception as e:
                continue
        msg.empty(); bar.empty()
        if not st.session_state.hits_1:
            st.warning(f"RSI {thr} 以下の銘柄は見つかりませんでした。条件を緩めて再試行してください。")
        else:
            st.success(f"{len(st.session_state.hits_1)} 銘柄を見つけました。下のリストで確認・保存してください。")
        st.rerun()

    # 重複IDエラーを防ぐため key を固定
    sel1 = st.multiselect("監視リストに追加・保存", options, default=st.session_state.hits_1, key="multi_tab1")
    if st.button("💾 この内容を保存（タブ1）", key="save_tab1"):
        save_to_file(sel1)

with tab2:
    st.header("📊 RCI × RSI 複合分析")
    st.write("RSI低迷 × RCI大底（買い場）または RSI高騰 × RCI天井（売り場）を検知します。")
    if st.button("🔍 複合スキャン実行", key="btn_tab2"):
        st.session_state.hits_2 = []
        bar2 = st.progress(0); msg2 = st.empty(); tickers = list(JPX400_DICT.keys())
        for i, t in enumerate(tickers):
            bar2.progress((i + 1) / len(tickers))
            msg2.text(f"複合分析中: {t}")
            try:
                df = yf.download(t, period="4mo", interval="1d", progress=False)
                close_s = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                close_s = close_s.dropna()
                
                rsi = calculate_rsi(close_s).iloc[-1]
                rci = calculate_rci(close_s).iloc[-1]
                
                # 複合条件判定
                if (rsi <= 35 and rci <= -80) or (rsi >= 75 and rci >= 80):
                    name_full = f"{t} {JPX400_DICT[t]}"
                    st.session_state.hits_2.append(name_full)
                    st.session_state.reasons[t] = f"複合判定(RSI:{rsi:.1f}, RCI:{rci:.1f})"
            except: continue
        msg2.empty(); bar2.empty()
        st.rerun()

    sel2 = st.multiselect("監視リストに追加・保存", options, default=st.session_state.hits_2, key="multi_tab2")
    if st.button("💾 この内容を保存（タブ2）", key="save_tab2"):
        save_to_file(sel2)

with tab3:
    st.header("☀️ 監視リスト管理")
    if st.button("🗑️ 登録銘柄をすべて削除", type="primary", key="clear_all"):
        save_to_file([]); st.rerun()
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            watch_data = json.load(f)
            if watch_data:
                for item in watch_data:
                    st.write(f"🔹 **{item['ticker']} {item.get('name','')}**")
                    st.caption(f"理由: {item.get('reason','-')} / 登録: {item.get('at','-')}")
                    st.write("---")
            else:
                st.info("監視中の銘柄はありません。")
