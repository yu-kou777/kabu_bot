import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np
import time

# --- 基本設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：最強統合パネル", layout="wide")

# --- 便利関数 ---
def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def calculate_rci(series, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

def save_watchlist(selected_full, temp_data):
    final_list = []
    for full in selected_full:
        ticker = full.split(" ")[0]
        reason = temp_data.get(ticker, "手動追加")
        final_list.append({
            "ticker": ticker,
            "name": JPX400_DICT.get(ticker, ""),
            "reason": reason,
            "at": get_jst_now().strftime('%m/%d %H:%M')
        })
    with open(WATCHLIST_FILE, 'w') as f: json.dump(final_list, f)
    st.success(f"{len(final_list)}銘柄を保存しました。")
    return final_list

# --- UI：3タブ構成 ---
tab1, tab2, tab3 = st.tabs(["🌙 5日間RSIスキャン", "📊 RCI×RSI複合分析", "☀️ 監視中の銘柄状況"])

if 'temp_watchlist' not in st.session_state: st.session_state.temp_watchlist = {}
options = [f"{c} {n}" for c, n in JPX400_DICT.items()]

# --- TAB 1: 5日間RSIスキャン ---
with tab1:
    st.header("🌙 直近5日間の動きから抽出")
    threshold = st.slider("RSIしきい値", 10, 60, 40, key="rsi_5d")
    if st.button("🚀 5日間RSIスキャン開始"):
        hits = []
        data = yf.download(list(JPX400_DICT.keys()), period="2mo", interval="1d", group_by='ticker', progress=False)
        for t in JPX400_DICT.keys():
            try:
                df = data[t].dropna()
                rsi_s = calculate_rsi(df)
                min_rsi = rsi_s.tail(5).min()
                if min_rsi <= threshold:
                    st.session_state.temp_watchlist[t] = f"5日内RSI低迷({min_rsi:.1f})"
                    hits.append({"コード": t, "和名": JPX400_DICT[t], "5日最小RSI": round(min_rsi, 1)})
            except: continue
        if hits: st.table(pd.DataFrame(hits))
        else: st.warning("該当なし。")

    st.write("---")
    current_selected = [f"{t} {JPX400_DICT[t]}" for t in st.session_state.temp_watchlist.keys()]
    sel1 = st.multiselect("監視登録（手動追加も可）", options, default=current_selected, key="sel1")
    if st.button("💾 監視リストを保存", key="save1"):
        save_watchlist(sel1, st.session_state.temp_watchlist)

# --- TAB 2: RCI×RSI複合分析 (復活機能) ---
with tab2:
    st.header("📊 RCI × RSI 複合スキャナー（大底・天井）")
    col_a, col_b = st.columns(2)
    
    # データ一括取得
    if col_a.button("🔍 複合分析（全銘柄スキャン）"):
        hits_bottom = []; hits_ceiling = []
        data = yf.download(list(JPX400_DICT.keys()), period="3mo", interval="1d", group_by='ticker', progress=False)
        for t in JPX400_DICT.keys():
            try:
                df = data[t].dropna()
                rsi = calculate_rsi(df).iloc[-1]
                rci9 = calculate_rci(df['Close'], 9).iloc[-1]
                
                # ① 大底狙い: RSI <= 35 かつ RCI <= -80
                if rsi <= 35 and rci9 <= -80:
                    st.session_state.temp_watchlist[t] = "複合・大底狙い"
                    hits_bottom.append(f"{t} {JPX400_DICT[t]} (RSI:{rsi:.1f}, RCI:{rci9:.1f})")
                # ② 天井狙い: RSI >= 70 かつ RCI >= 80
                elif rsi >= 70 and rci9 >= 80:
                    st.session_state.temp_watchlist[t] = "複合・天井狙い"
                    hits_ceiling.append(f"{t} {JPX400_DICT[t]} (RSI:{rsi:.1f}, RCI:{rci9:.1f})")
            except: continue
        
        st.subheader("🔵 ①大底狙い（RSI低迷×RCI最低）")
        if hits_bottom: 
            for h in hits_bottom: st.write(f"✅ {h}")
        else: st.info("該当なし")
        
        st.subheader("🔴 ②天井狙い（RSI高騰×RCI最高）")
        if hits_ceiling:
            for h in hits_ceiling: st.write(f"⚠️ {h}")
        else: st.info("該当なし")

    st.write("---")
    current_selected2 = [f"{t} {JPX400_DICT[t]}" for t in st.session_state.temp_watchlist.keys()]
    sel2 = st.multiselect("監視登録（手動追加も可）", options, default=current_selected2, key="sel2")
    if st.button("💾 監視リストを保存", key="save2"):
        save_watchlist(sel2, st.session_state.temp_watchlist)

# --- TAB 3: 監視中の銘柄状況 ---
with tab3:
    st.header("☀️ リアルタイム監視中の銘柄")
    if st.button("🗑️ 登録銘柄をすべて削除", type="primary"):
        with open(WATCHLIST_FILE, 'w') as f: json.dump([], f)
        st.session_state.temp_watchlist = {}
        st.rerun()

    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f:
            watch_data = json.load(f)
        for item in watch_data:
            reason = item.get('reason', '手動追加')
            color = "🔴" if "天井" in reason or "高騰" in reason else "🔵" if "大底" in reason or "RSI" in reason else "⚪"
            st.write(f"{color} **{item['ticker']} {item.get('name', '')}**")
            st.caption(f"監視理由: {reason} / 登録: {item.get('at', '-')}")
            st.write("---")
