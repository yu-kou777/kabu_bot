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

st.set_page_config(page_title="Jack株AI：完全定着版", layout="wide")

# --- ✅ 銘柄を定着させるためのメモリ（Session State）設定 ---
if 'confirmed_hits' not in st.session_state:
    st.session_state.confirmed_hits = []
if 'hit_reasons' not in st.session_state:
    st.session_state.hit_reasons = {}

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(series):
    if len(series) < 15: return pd.Series([np.nan] * len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    return 100 - (100 / (1 + (gain / loss)))

def save_list(selected_full_names):
    data = []
    for full in selected_full_names:
        code = full.split(" ")[0]
        data.append({
            "ticker": code,
            "name": JPX400_DICT.get(code, ""),
            "reason": st.session_state.hit_reasons.get(code, "5日RSI低迷"),
            "at": get_jst_now().strftime('%m/%d %H:%M')
        })
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    st.success(f"✅ {len(data)} 銘柄をファイルに保存しました！月曜日から監視を開始します。")

# --- UI ---
tab1, tab2 = st.tabs(["🔍 5日RSI検索・保存", "☀️ 監視状況の確認"])
options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 銘柄スキャン ＆ 監視登録")
    st.write("スキャン開始後、ヒットした銘柄は下の選択枠に「自動で固定」されます。確認して保存してください。")
    thr = st.slider("しきい値（RSI）", 10, 85, 70, key="slider_rsi")
    
    if st.button("🚀 スキャンを開始する", key="btn_scan"):
        # スキャン開始時に一度リセット
        new_hits = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar.progress((i+1)/len(JPX400_DICT))
            status.text(f"分析中: {t} {n}")
            try:
                df = yf.download(t, period="3mo", progress=False)
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                rsi_s = calculate_rsi(close.dropna())
                min_rsi = rsi_s.tail(5).min()
                
                if min_rsi <= thr:
                    name_full = f"{t} {n}"
                    new_hits.append(name_full)
                    st.session_state.hit_reasons[t] = f"5日内最小RSI:{min_rsi:.1f}"
            except: continue
        
        # ✅ スキャン結果をSession Stateに保存（これで画面がリロードされても消えません）
        st.session_state.confirmed_hits = new_hits
        status.empty(); bar.empty()
        st.rerun() # 結果をmultiselectに反映させるために再描画
    
    # ✅ Session Stateにある銘柄を初期値(default)として表示
    sel = st.multiselect("監視候補（スキャン結果が自動で入ります）", options, default=st.session_state.confirmed_hits, key="multiselect_box")
    
    # ユーザーがmultiselectを操作した場合、その状態を保持
    st.session_state.confirmed_hits = sel

    if st.button("💾 この内容で監視リストを確定保存", key="btn_save"):
        if not sel:
            st.warning("銘柄が選択されていません。")
        else:
            save_list(sel)

with tab2:
    st.header("☀️ 現在の監視リスト")
    if st.button("🗑️ リストを全削除", type="primary"):
        st.session_state.confirmed_hits = []
        save_list([]); st.rerun()
        
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            watch_data = json.load(f)
            if not watch_data:
                st.info("現在、監視中の銘柄はありません。")
            for item in watch_data:
                st.write(f"🔹 **{item['ticker']} {item.get('name')}**")
                st.caption(f"理由: {item.get('reason')} / 登録: {item.get('at')}")
                st.write("---")
