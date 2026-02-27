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

st.set_page_config(page_title="Jack株AI：完全定着版", layout="wide")

# --- メモリの初期化 ---
if 'locked_hits' not in st.session_state:
    st.session_state.locked_hits = []
if 'reason_logs' not in st.session_state:
    st.session_state.reason_logs = {}

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(series):
    if len(series) < 15: return pd.Series([np.nan] * len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- UI ---
tab1, tab2 = st.tabs(["🔍 5日RSI検索 ＆ 登録", "☀️ 監視状況の確認"])
options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 銘柄スキャン ＆ 監視登録")
    st.write("スキャンが完了すると、銘柄が自動的に下の枠へ「定着」します。")
    thr = st.slider("しきい値（RSI）", 10, 85, 75, key="rsi_slider")
    
    if st.button("🚀 スキャンを開始（定着ロック機能付き）", key="scan_button"):
        temp_list = []
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
                    temp_list.append(name_full)
                    st.session_state.reason_logs[t] = f"5日内最小RSI:{min_rsi:.1f}"
            except: continue
        
        # ✅ ここでメモリにガッチリ保存
        st.session_state.locked_hits = temp_list
        status.empty(); bar.empty()
        st.rerun() # リストを枠に反映させるために再描画
    
    # default引数にlocked_hitsを渡すことで、銘柄が「選択された状態」で維持されます
    sel = st.multiselect("監視リスト（スキャン結果が自動で入ります）", options, default=st.session_state.locked_hits, key="select_box")
    
    # ユーザーが枠内で銘柄を消したり足したりした場合、その状態をメモリへ上書き
    st.session_state.locked_hits = sel

    if st.button("💾 この内容を監視リストに保存", key="save_button"):
        if not sel:
            st.warning("銘柄が選択されていません。")
        else:
            final_data = []
            for full in sel:
                code = full.split(" ")[0]
                final_data.append({
                    "ticker": code,
                    "name": JPX400_DICT.get(code, ""),
                    "reason": st.session_state.reason_logs.get(code, "5日RSI低迷"),
                    "at": get_jst_now().strftime('%m/%d %H:%M')
                })
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            st.success(f"✅ {len(final_data)} 銘柄を保存しました！")

with tab2:
    st.header("☀️ 現在の監視リスト")
    if st.button("🗑️ 全削除", type="primary"):
        st.session_state.locked_hits = []
        with open(WATCHLIST_FILE, 'w') as f: json.dump([], f)
        st.rerun()
        
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            watch_data = json.load(f)
            for item in watch_data:
                st.write(f"🔹 **{item['ticker']} {item.get('name')}**")
                st.caption(f"理由: {item.get('reason')} / 登録: {item.get('at')}")
                st.write("---")
