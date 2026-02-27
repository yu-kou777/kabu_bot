import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, time as dt_time, timedelta, timezone
import time
import numpy as np

# --- 基本設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：究極統合パネル", layout="wide")

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rci(series, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f: return json.load(f)
        except: return []
    return []

# --- UI：明日の準備タブ ---
tab1, tab2 = st.tabs(["🌙 明日の選別・登録", "☀️ リアルタイム監視状況"])

with tab1:
    st.header("🌙 明日の仕込み：銘柄スキャナー")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("① RSI条件で探す")
        rsi_val = st.slider("RSIのしきい値", 10, 80, 40, help="この数値以下の銘柄を探します")
        if st.button("🔍 RSI条件に合う銘柄をスキャン"):
            found = []
            bar = st.progress(0); t_list = list(JPX400_DICT.keys())
            all_d = yf.download(t_list, period="1mo", interval="1d", group_by='ticker', progress=False)
            for i, t in enumerate(t_list):
                bar.progress((i+1)/len(t_list))
                try:
                    df = all_d[t].dropna()
                    delta = df['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    rsi = 100 - (100 / (1 + (gain / loss)))
                    if rsi.iloc[-1] <= rsi_val: found.append(f"{t} {JPX400_DICT[t]}")
                except: continue
            st.session_state.hits = found

    with col2:
        st.subheader("② RCI複合分析で探す")
        if st.button("🔍 JPX400銘柄を一斉複合スキャン"):
            found = []
            bar = st.progress(0); t_list = list(JPX400_DICT.keys())
            all_d = yf.download(t_list, period="100d", interval="1d", group_by='ticker', progress=False)
            for i, t in enumerate(t_list):
                bar.progress((i+1)/len(t_list))
                try:
                    df = all_d[t].dropna()
                    r9 = calculate_rci(df['Close'], 9)
                    # 判定ロジック：RCI底打ち等
                    if r9.iloc[-1] > r9.iloc[-2] and r9.iloc[-2] < -80: found.append(f"{t} {JPX400_DICT[t]}")
                except: continue
            st.session_state.hits = found

    st.write("---")
    st.subheader("✅ 監視銘柄の登録")
    options = [f"{c} {n}" for c, n in JPX400_DICT.items()]
    hits = st.session_state.get('hits', [])
    
    # 検索結果を自動で反映
    selected = st.multiselect("監視リストに追加（手動追加も可能）", options, default=hits)
    
    if st.button("💾 監視リストを保存して開始"):
        if selected:
            codes = [x.split(" ")[0] for x in selected]
            data = [{"ticker": t, "added_date": get_jst_now().strftime('%Y-%m-%d')} for t in codes]
            with open(WATCHLIST_FILE, 'w') as f: json.dump(data, f)
            st.success(f"【成功】{len(codes)}銘柄を保存しました！")
            requests.post(DISCORD_URL, json={"content": f"▶️ 監視リスト更新: {len(codes)}銘柄"})
        else:
            st.error("銘柄を選んでください。")

with tab2:
    jst_now = get_jst_now()
    st.subheader(f"🕰 現在時刻: {jst_now.strftime('%H:%M:%S')}")
    watch_data = load_watchlist()
    if watch_data:
        st.info(f"現在 {len(watch_data)} 銘柄を裏側で監視中です。")
        for item in watch_data: st.write(f"・{item['ticker']} {JPX400_DICT.get(item['ticker'])}")
