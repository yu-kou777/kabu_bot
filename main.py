import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np
import traceback

# --- 基本設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：スキャン修正版", layout="wide")

if 'reasons' not in st.session_state: st.session_state.reasons = {}
if 'last_hits' not in st.session_state: st.session_state.last_hits = []

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# RSI計算
def calculate_rsi(df):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

# RCI計算
def calculate_rci(series, period=9):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

def safe_save(selected_list):
    try:
        final_data = []
        for full_name in selected_list:
            ticker = full_name.split(" ")[0]
            reason = st.session_state.reasons.get(ticker, "手動追加")
            final_data.append({
                "ticker": ticker,
                "name": JPX400_DICT.get(ticker, "不明"),
                "reason": reason,
                "at": get_jst_now().strftime('%m/%d %H:%M')
            })
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        st.success(f"✅ {len(final_data)}銘柄を保存しました。")
        return True
    except:
        st.error("保存失敗")
        return False

# --- UI ---
tab1, tab2, tab3 = st.tabs(["🌙 5日RSI検索", "📊 RCI複合分析", "☀️ 監視リスト管理"])

options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 直近5日間のRSIで探す")
    thr = st.slider("RSIしきい値", 10, 80, 50, key="s1")
    if st.button("🚀 RSIスキャン開始"):
        hits = []
        bar = st.progress(0)
        tickers = list(JPX400_DICT.keys())
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers))
            try:
                # 1銘柄ずつ確実に取得
                df = yf.download(t, period="2mo", progress=False)
                if df.empty: continue
                
                # yfinanceの新しいデータ構造に対応（Close列の抽出）
                close_series = df['Close']
                if isinstance(close_series, pd.DataFrame): close_series = close_series.iloc[:, 0]
                
                rsi_s = calculate_rsi(close_series.dropna())
                m = rsi_s.tail(5).min()
                
                if m <= thr:
                    st.session_state.reasons[t] = f"5日内RSI低迷({m:.1f})"
                    hits.append(f"{t} {JPX400_DICT[t]} (RSI:{m:.1f})")
            except: continue
        st.session_state.last_hits = hits
        if not hits: st.warning("該当する銘柄が見つかりませんでした。しきい値を上げてください。")
    
    selected1 = st.multiselect("保存する銘柄を選択", options, default=st.session_state.get('last_hits', []), key="m1")
    if st.button("💾 リストを保存（タブ1）"): safe_save(selected1)

with tab2:
    st.header("📊 RCI × RSI 複合スキャン")
    if st.button("🔍 複合分析（大底・天井）"):
        b_hits, c_hits = [], []
        bar2 = st.progress(0)
        tickers = list(JPX400_DICT.keys())
        for i, t in enumerate(tickers):
            bar2.progress((i + 1) / len(tickers))
            try:
                df = yf.download(t, period="3mo", progress=False)
                if df.empty: continue
                close_s = df['Close']
                if isinstance(close_s, pd.DataFrame): close_s = close_s.iloc[:, 0]
                
                rsi = calculate_rsi(close_s.dropna()).iloc[-1]
                rci = calculate_rci(close_s.dropna()).iloc[-1]
                
                if rsi <= 35 and rci <= -80:
                    st.session_state.reasons[t] = "複合・大底狙い"
                    b_hits.append(f"{t} {JPX400_DICT[t]}")
                elif rsi >= 70 and rci >= 80:
                    st.session_state.reasons[t] = "複合・天井狙い"
                    c_hits.append(f"{t} {JPX400_DICT[t]}")
            except: continue
        st.session_state.last_hits2 = b_hits + c_hits
        st.write(f"🔵 大底候補: {len(b_hits)}銘柄 / 🔴 天井候補: {len(c_hits)}銘柄")

    selected2 = st.multiselect("保存する銘柄を選択", options, default=st.session_state.get('last_hits2', []), key="m2")
    if st.button("💾 リストを保存（タブ2）"): safe_save(selected2)

with tab3:
    st.header("☀️ 現在の監視リスト")
    if st.button("🗑️ 全銘柄を削除する", type="primary"):
        if safe_save([]): st.rerun()

    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            watch_data = json.load(f)
        for item in watch_data:
            st.write(f"🔹 **{item['ticker']} {item.get('name','')}**")
            st.caption(f"理由: {item.get('reason','-')} / 登録: {item.get('at','-')}")
            st.write("---")
