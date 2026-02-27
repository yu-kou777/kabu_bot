import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import time
import numpy as np

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：複合分析パネル", layout="wide")

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# --- 指標計算関数 ---
def calculate_rci(series, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

def get_composite_indicators(tickers):
    data = yf.download(tickers, period="3mo", interval="1d", group_by='ticker', progress=False)
    results = {}
    for t in tickers:
        try:
            df = data[t].dropna()
            if len(df) < 20: continue
            # RSI(14)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]
            # RCI(9)
            rci9 = calculate_rci(df['Close'], 9).iloc[-1]
            results[t] = {"rsi": rsi, "rci9": rci9}
        except: continue
    return results

# --- UI：操作タブ ---
tab1, tab2 = st.tabs(["🌙 複合検索・一括登録", "☀️ 監視中の銘柄状況"])

with tab1:
    st.header("🌙 RSI × RCI 複合分析スキャナー")
    if 'temp_watchlist' not in st.session_state: st.session_state.temp_watchlist = {}
    if 'scan_results' not in st.session_state: st.session_state.scan_results = []

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔵 大底狙い（RSI低迷 × RCI最低）")
        if st.button("🔍 絶好の買い場銘柄を検索"):
            st.session_state.scan_results = []
            indicators = get_composite_indicators(list(JPX400_DICT.keys()))
            for t, v in indicators.items():
                # 条件：RSI 35以下 ＆ RCI(9) -80以下
                if v['rsi'] <= 35 and v['rci9'] <= -80:
                    st.session_state.temp_watchlist[t] = "低RSI×低RCI"
                    st.session_state.scan_results.append(f"✅ {t} {JPX400_DICT[t]} (RSI:{v['rsi']:.1f}, RCI:{v['rci9']:.1f})")
            if not st.session_state.scan_results: st.warning("現在、大底条件に合う銘柄はありません。")

    with col2:
        st.subheader("🔴 天井狙い（RSI高騰 × RCI最高）")
        if st.button("🔍 警戒の売り場銘柄を検索"):
            st.session_state.scan_results = []
            indicators = get_composite_indicators(list(JPX400_DICT.keys()))
            for t, v in indicators.items():
                # 条件：RSI 70以上 ＆ RCI(9) 80以上
                if v['rsi'] >= 70 and v['rci9'] >= 80:
                    st.session_state.temp_watchlist[t] = "高RSI×高RCI"
                    st.session_state.scan_results.append(f"⚠️ {t} {JPX400_DICT[t]} (RSI:{v['rsi']:.1f}, RCI:{v['rci9']:.1f})")
            if not st.session_state.scan_results: st.warning("現在、天井条件に合う銘柄はありません。")

    if st.session_state.scan_results:
        with st.expander("🔍 スキャン結果の確認", expanded=True):
            for res in st.session_state.scan_results: st.write(res)

    st.write("---")
    options = [f"{c} {n}" for c, n in JPX400_DICT.items()]
    current_hits = [f"{t} {JPX400_DICT[t]}" for t in st.session_state.temp_watchlist.keys()]
    selected_full = st.multiselect("監視リストに追加・確認", options, default=current_hits)
    
    if st.button("💾 この内容で監視を保存"):
        final_list = []
        for full in selected_full:
            ticker = full.split(" ")[0]
            reason = st.session_state.temp_watchlist.get(ticker, "手動追加")
            final_list.append({"ticker": ticker, "name": JPX400_DICT[ticker], "reason": reason, "at": get_jst_now().strftime('%m/%d %H:%M')})
        with open(WATCHLIST_FILE, 'w') as f: json.dump(final_list, f)
        st.success(f"{len(final_list)}銘柄を保存しました。")
        st.session_state.temp_watchlist = {}; st.session_state.scan_results = []

with tab2:
    st.header("☀️ 現在の監視リスト")
    if st.button("🗑️ 登録銘柄をすべて削除", type="primary"):
        with open(WATCHLIST_FILE, 'w') as f: json.dump([], f)
        st.rerun()

    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f:
            watch_data = json.load(f)
        for item in watch_data:
            reason = item.get('reason', '手動追加')
            color = "🔴" if "高" in reason else "🔵" if "低" in reason else "⚪"
            st.write(f"{color} **{item['ticker']} {item.get('name', '')}**")
            st.caption(f"理由: {reason} / 登録: {item.get('at', '-')}")
            st.write("---")
