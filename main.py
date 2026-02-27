import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np

# --- 基本設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
TEMP_DATA_FILE = "temp_scan_results.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

# スマホ向け：centeredレイアウト
st.set_page_config(page_title="Jack株AI", layout="centered")

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

# --- UI：目的別の3タブ構成 ---
tab1, tab2, tab3 = st.tabs(["🔍 5日RSI検索", "📊 RCI×RSI複合", "📋 監視リスト"])

# セッション状態の初期化
if 'reasons' not in st.session_state: st.session_state.reasons = {}

with tab1:
    st.header("🌙 直近5日間の底打ち検知")
    thr1 = st.slider("しきい値(RSI)", 10, 85, 75, key="s1")
    if st.button("🚀 5日検索スキャン開始", use_container_width=True):
        hits = []
        bar = st.progress(0)
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar.progress((i+1)/len(JPX400_DICT))
            try:
                df = yf.download(t, period="3mo", progress=False)
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                rsi = calculate_rsi(close.dropna()).tail(5).min()
                if rsi <= thr1:
                    hits.append(f"{t} {n}")
                    st.session_state.reasons[t] = f"5日RSI低迷({rsi:.1f})"
            except: continue
        with open(TEMP_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(hits, f, ensure_ascii=False)
        st.rerun()

with tab2:
    st.header("📊 RSI×RCI 複合スキャン")
    st.caption("日足の「大底」と「天井」を同時に探します")
    col1, col2 = st.columns(2)
    rsi_low = col1.number_input("RSI(下限)", 10, 50, 35)
    rci_low = col2.number_input("RCI(下限)", -100, 0, -80)
    
    if st.button("🔍 複合スキャン実行", use_container_width=True):
        hits = []
        bar = st.progress(0)
        for i, (t, n) in enumerate(JPX400_DICT.items()):
            bar.progress((i+1)/len(JPX400_DICT))
            try:
                df = yf.download(t, period="4mo", progress=False)
                close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                close_d = close.dropna()
                rv = calculate_rsi(close_d).iloc[-1]
                rcv = calculate_rci(close_d).iloc[-1]
                if rv <= rsi_low and rcv <= rci_low:
                    hits.append(f"{t} {n}")
                    st.session_state.reasons[t] = f"複合大底(RSI:{rv:.1f},RCI:{rcv:.1f})"
                elif rv >= 70 and rcv >= 80:
                    hits.append(f"{t} {n}")
                    st.session_state.reasons[t] = f"複合天井(RSI:{rv:.1f},RCI:{rcv:.1f})"
            except: continue
        with open(TEMP_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(hits, f, ensure_ascii=False)
        st.rerun()

# --- 共通の保存エリア ---
st.write("---")
current_hits = []
if os.path.exists(TEMP_DATA_FILE):
    with open(TEMP_DATA_FILE, 'r', encoding='utf-8') as f:
        current_hits = json.load(f)

# スマホでも選びやすいよう container_width を活用
sel = st.multiselect("監視に登録する銘柄を選択", [f"{k} {v}" for k, v in JPX400_DICT.items()], default=current_hits)

if st.button("💾 監視リストを確定保存", type="primary", use_container_width=True):
    final = []
    for full in sel:
        code = full.split(" ")[0]
        final.append({"ticker": code, "name": JPX400_DICT.get(code, ""), "reason": st.session_state.reasons.get(code, "手動登録"), "at": get_jst_now().strftime('%m/%d %H:%M')})
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    st.success(f"✅ {len(final)} 銘柄を保存完了！")

with tab3:
    st.header("📋 現在の監視リスト")
    if st.button("🗑️ リストを空にする", use_container_width=True):
        with open(WATCHLIST_FILE, 'w') as f: json.dump([], f)
        st.rerun()
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            for item in json.load(f):
                st.write(f"🔹 **{item['ticker']} {item.get('name')}**")
                st.caption(f"理由: {item.get('reason')} / {item.get('at')}")
