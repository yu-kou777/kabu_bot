import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：完全統合版", layout="wide")

# セッション管理（スキャン結果を保持）
if 'reasons' not in st.session_state: st.session_state.reasons = {}
if 'hits_tab1' not in st.session_state: st.session_state.hits_tab1 = []
if 'hits_tab2' not in st.session_state: st.session_state.hits_tab2 = []

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

def save_list(selected_full):
    data = []
    for full in selected_full:
        code = full.split(" ")[0]
        reason = st.session_state.reasons.get(code, "手動登録")
        data.append({"ticker": code, "name": JPX400_DICT.get(code, ""), "reason": reason, "at": get_jst_now().strftime('%m/%d %H:%M')})
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    st.success(f"✅ {len(data)} 銘柄を保存しました！")

# --- UI ---
tab1, tab2, tab3 = st.tabs(["🌙 5日RSI検索", "📊 RCI複合分析", "☀️ 監視リスト管理"])
options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 直近5日間のRSIで探す")
    thr = st.slider("RSIしきい値", 10, 80, 55, key="s1")
    if st.button("🚀 RSIスキャン開始"):
        hits_for_table, hits_for_select = [], []
        bar = st.progress(0)
        tickers = list(JPX400_DICT.keys())
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers))
            try:
                df = yf.download(t, period="2mo", progress=False)
                if df.empty: continue
                # 最新のyfinanceデータ形式(Series)に強制変換
                close_s = df['Close'].squeeze().dropna()
                rsi_s = calculate_rsi(close_s)
                min_rsi = rsi_s.tail(5).min()
                if min_rsi <= thr:
                    name_full = f"{t} {JPX400_DICT[t]}"
                    st.session_state.reasons[t] = f"5日RSI低迷({min_rsi:.1f})"
                    hits_for_table.append({"銘柄": name_full, "最小RSI": round(min_rsi, 1)})
                    hits_for_select.append(name_full)
            except: continue
        st.session_state.hits_tab1 = hits_for_select
        if hits_for_table: st.table(pd.DataFrame(hits_for_table))
        else: st.warning("該当なし")

    sel1 = st.multiselect("監視リストに追加", options, default=st.session_state.hits_tab1, key="m1")
    if st.button("💾 保存（タブ1）"): save_list(sel1)

with tab2:
    st.header("📊 RCI × RSI 複合分析")
    if st.button("🔍 複合スキャン実行"):
        hits_for_select2 = []
        bar2 = st.progress(0); tickers = list(JPX400_DICT.keys())
        for i, t in enumerate(tickers):
            bar2.progress((i + 1) / len(tickers))
            try:
                df = yf.download(t, period="3mo", progress=False)
                close_s = df['Close'].squeeze().dropna()
                rsi = calculate_rsi(close_s).iloc[-1]
                rci = calculate_rci(close_s).iloc[-1]
                if (rsi <= 35 and rci <= -80) or (rsi >= 70 and rci >= 80):
                    name_full = f"{t} {JPX400_DICT[t]}"
                    st.session_state.reasons[t] = f"複合判定(RSI:{rsi:.1f}, RCI:{rci:.1f})"
                    hits_for_select2.append(name_full)
            except: continue
        st.session_state.hits_tab2 = hits_for_select2
        st.write(f"結果: {len(hits_for_select2)} 銘柄検知")

    sel2 = st.multiselect("監視リストに追加", options, default=st.session_state.hits_tab2, key="m2")
    if st.button("💾 保存（タブ2）"): save_list(sel2)

with tab3:
    st.header("☀️ 監視リストの削除・管理")
    if st.button("🗑️ 全銘柄を削除", type="primary"):
        save_list([]); st.rerun()
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            for item in json.load(f):
                st.write(f"🔹 **{item['ticker']} {item.get('name')}** ({item.get('reason')})")
