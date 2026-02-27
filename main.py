import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np

# --- 銘柄設定 ---
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}
WATCHLIST_FILE = "jack_watchlist.json"

st.set_page_config(page_title="Jack株AI：超安定版", layout="wide")

# セッション状態の管理
if 'scan_hits' not in st.session_state: st.session_state.scan_hits = []
if 'hit_reasons' not in st.session_state: st.session_state.hit_reasons = {}

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# --- 確実な指標計算 ---
def calculate_indicators(df):
    close = df['Close'].dropna()
    # RSI計算
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain / loss)))
    # RCI計算
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    rci = close.rolling(9).apply(rci_func)
    return rsi, rci

# --- UI ---
tab1, tab2, tab3 = st.tabs(["🌙 5日RSI検索", "📊 RCI複合分析", "☀️ 監視リスト管理"])

options = [f"{k} {v}" for k, v in JPX400_DICT.items()]

with tab1:
    st.header("🌙 直近5日間のRSIで探す")
    thr = st.slider("RSIしきい値", 10, 80, 60, key="slider_rsi_5d")
    
    if st.button("🚀 RSIスキャン開始", key="btn_rsi_5d"):
        st.session_state.scan_hits = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, (code, name) in enumerate(JPX400_DICT.items()):
            bar.progress((i + 1) / len(JPX400_DICT))
            status.info(f"分析中: {code} {name} ...")
            try:
                # 取得を1銘柄ずつ確実に
                df = yf.download(code, period="3mo", interval="1d", progress=False)
                if df.empty: continue
                
                # yfinanceの構造問題を解決
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                rsi, _ = calculate_indicators(df)
                min_rsi = rsi.tail(5).min()
                
                if min_rsi <= thr:
                    full_name = f"{code} {name}"
                    st.session_state.scan_hits.append(full_name)
                    st.session_state.hit_reasons[code] = f"5日RSI低迷({min_rsi:.1f})"
                    st.write(f"✅ ヒット: {full_name} (最小RSI: {min_rsi:.1f})")
            except Exception as e:
                continue
        
        status.success(f"完了！ {len(st.session_state.scan_hits)}銘柄見つかりました。")
        st.rerun()

    # スキャン結果を自動選択
    sel1 = st.multiselect("監視リストに追加", options, default=st.session_state.scan_hits, key="ms_tab1")
    if st.button("💾 保存", key="save_tab1"):
        final_list = []
        for s in sel1:
            c = s.split(" ")[0]
            final_list.append({"ticker": c, "name": JPX400_DICT[c], "reason": st.session_state.hit_reasons.get(c, "手動追加"), "at": get_jst_now().strftime('%m/%d %H:%M')})
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, ensure_ascii=False, indent=2)
        st.success("保存しました！")

with tab2:
    st.header("📊 RCI × RSI 複合分析")
    if st.button("🔍 複合スキャン実行", key="btn_composite"):
        st.session_state.scan_hits_comp = []
        bar2 = st.progress(0)
        status2 = st.empty()
        for i, (code, name) in enumerate(JPX400_DICT.items()):
            bar2.progress((i + 1) / len(JPX400_DICT))
            status2.info(f"分析中: {code} ...")
            try:
                df = yf.download(code, period="4mo", interval="1d", progress=False)
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                rsi, rci = calculate_indicators(df)
                l_rsi, l_rci = rsi.iloc[-1], rci.iloc[-1]
                
                if (l_rsi <= 35 and l_rci <= -80) or (l_rsi >= 75 and l_rci >= 80):
                    full_name = f"{code} {name}"
                    st.session_state.scan_hits_comp.append(full_name)
                    st.session_state.hit_reasons[code] = f"複合(RSI:{l_rsi:.1f}, RCI:{l_rci:.1f})"
                    st.write(f"✨ 転換点検知: {full_name}")
            except: continue
        status2.success("完了！")
        st.rerun()

    sel2 = st.multiselect("監視リストに追加", options, default=st.session_state.get('scan_hits_comp', []), key="ms_tab2")
    if st.button("💾 保存", key="save_tab2"):
        # tab1と同様の保存処理
        pass

with tab3:
    st.header("☀️ 監視リスト管理")
    if st.button("🗑️ 全削除", type="primary"):
        with open(WATCHLIST_FILE, 'w') as f: json.dump([], f)
        st.rerun()
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            for item in json.load(f):
                st.write(f"🔹 **{item['ticker']} {item.get('name','')}** ({item.get('reason','')})")
