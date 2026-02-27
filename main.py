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

st.set_page_config(page_title="Jack株AI：検出固定版", layout="wide")

# メモリ（セッション）の初期化
if 'detected_stocks' not in st.session_state: st.session_state.detected_stocks = []
if 'reasons' not in st.session_state: st.session_state.reasons = {}

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- UI ---
tab1, tab2 = st.tabs(["🔍 銘柄スキャン ＆ 登録", "📋 現在の監視リスト"])

with tab1:
    st.header("🌙 RSIスキャナー（直近5日間の底打ちを検知）")
    thr = st.slider("しきい値（RSI）", 10, 80, 60, key="thr_slider")
    
    if st.button("🚀 スキャン開始", key="scan_start"):
        new_hits = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar.progress((i+1)/len(JPX400_DICT))
            status.text(f"分析中: {t} {n}")
            try:
                df = yf.download(t, period="3mo", progress=False)
                # MultiIndex対策：Close列を正確に取得
                if 'Close' in df.columns:
                    close = df['Close']
                    if isinstance(close, pd.DataFrame): close = close.iloc[:, 0]
                    rsi_s = calculate_rsi(close.dropna())
                    min_rsi = rsi_s.tail(5).min()
                    
                    if min_rsi <= thr:
                        name_full = f"{t} {n}"
                        new_hits.append(name_full)
                        st.session_state.reasons[t] = f"5日RSI低迷({min_rsi:.1f})"
            except: continue
        
        st.session_state.detected_stocks = list(set(new_hits)) # 重複排除して保存
        status.empty(); bar.empty()

    st.write("---")
    st.subheader("💡 検出された銘柄（ここから選んで保存してください）")
    
    # 検出されたものをデフォルト値として設定
    all_options = [f"{k} {v}" for k, v in JPX400_DICT.items()]
    selected = st.multiselect("監視リストに追加", all_options, default=st.session_state.detected_stocks)

    if st.button("💾 この内容で監視を確定（保存）"):
        final_data = []
        for full in selected:
            code = full.split(" ")[0]
            final_data.append({
                "ticker": code,
                "name": JPX400_DICT.get(code, ""),
                "reason": st.session_state.reasons.get(code, "手動登録"),
                "at": get_jst_now().strftime('%m/%d %H:%M')
            })
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        st.success(f"✅ {len(final_data)} 銘柄を監視リストに保存しました！")

with tab2:
    st.header("☀️ リアルタイム監視中の銘柄")
    if st.button("🗑️ リストを空にする", type="primary"):
        with open(WATCHLIST_FILE, 'w') as f: json.dump([], f)
        st.session_state.detected_stocks = []
        st.rerun()
    
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            for item in json.load(f):
                st.write(f"🔹 **{item['ticker']} {item.get('name')}**")
                st.caption(f"理由: {item.get('reason')} / 登録: {item.get('at')}")
