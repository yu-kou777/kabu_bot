import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np

# --- 基本設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：5日RSIスキャナー", layout="wide")

# セッション状態（メモリ）の初期化
if 'hits_5d' not in st.session_state: st.session_state.hits_5d = []
if 'reasons' not in st.session_state: st.session_state.reasons = {}

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# 自前計算RSI（安定性重視）
def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

def save_list(selected_full_names):
    data = []
    for full in selected_full_names:
        code = full.split(" ")[0]
        reason = st.session_state.reasons.get(code, "手動登録")
        data.append({
            "ticker": code,
            "name": JPX400_DICT.get(code, ""),
            "reason": reason,
            "at": get_jst_now().strftime('%m/%d %H:%M')
        })
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    st.success(f"✅ {len(data)} 銘柄を保存しました！")

# --- UI ---
tab1, tab2 = st.tabs(["🔍 5日RSI検索・登録", "☀️ 監視リスト管理"])
options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 直近5日間のRSI低迷を探す")
    st.write("過去5日間の日足で、一度でもしきい値を下回った銘柄を抽出します。")
    thr = st.slider("RSIしきい値", 10, 85, 60, key="slider1")
    
    if st.button("🚀 スキャン開始", key="btn1"):
        st.session_state.hits_5d = [] # リセット
        bar = st.progress(0); status = st.empty()
        tickers = list(JPX400_DICT.items())
        
        for i, (t, n) in enumerate(tickers):
            bar.progress((i+1)/len(tickers))
            status.text(f"分析中: {t} {n}")
            try:
                # 1銘柄ずつ確実に取得
                df = yf.download(t, period="3mo", progress=False)
                if df.empty: continue
                
                # データの抽出（MultiIndex対策）
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                rsi_s = calculate_rsi(close.dropna())
                min_val = rsi_s.tail(5).min()
                
                if min_val <= thr:
                    name_full = f"{t} {n}"
                    st.session_state.hits_5d.append(name_full)
                    st.session_state.reasons[t] = f"5日RSI低迷({min_val:.1f})"
            except: continue
            
        status.empty(); bar.empty()
        if st.session_state.hits_5d:
            st.success(f"{len(st.session_state.hits_5d)}銘柄を検知しました。")
        else:
            st.warning("条件に合う銘柄は見つかりませんでした。しきい値を上げてください。")
        st.rerun()
    
    # スキャン結果を自動で入力枠に入れる
    sel1 = st.multiselect("監視に追加（ここに入った銘柄を保存します）", options, default=st.session_state.hits_5d, key="ms1")
    if st.button("💾 この内容を保存して開始", key="sv1"):
        save_list(sel1)

with tab2:
    st.header("☀️ 現在の監視リスト")
    if st.button("🗑️ 登録をすべて削除", type="primary"):
        st.session_state.hits_5d = []
        save_list([]); st.rerun()
        
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            watch_data = json.load(f)
            if not watch_data:
                st.info("監視中の銘柄はありません。")
            for item in watch_data:
                st.write(f"🔹 **{item['ticker']} {item.get('name')}**")
                st.caption(f"理由: {item.get('reason')} / 登録: {item.get('at')}")
                st.write("---")
