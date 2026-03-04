import streamlit as st
import json
import os
import yfinance as yf
import pandas as pd
import numpy as np

# --- 設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI：司令塔", layout="wide")

# --- 共通計算関数 ---
def get_status(ticker):
    """現在の銘柄が法則にどれくらい近いか判定する"""
    try:
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        c = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        ma60, ma200 = c.rolling(60).mean(), c.rolling(200).mean()
        ma20 = c.rolling(20).mean(); std20 = c.rolling(20).std()
        bb_u2, bb_l3 = ma20 + std20*2, ma20 - std20*3
        
        now_p = float(c.iloc[-1])
        m60 = ma60.iloc[-1]
        m200 = ma200.iloc[-1]
        
        # 法則判定
        active_rules = []
        if now_p > m60:
            if now_p >= bb_u2.iloc[-1]: active_rules.append("法則1(警戒)")
            if abs(now_p - m60) / m60 < 0.001: active_rules.append("法則2(チャンス)")
        else:
            if now_p <= bb_l3.iloc[-1]: active_rules.append("法則4(チャンス)")
            if abs(now_p - m200) / m200 < 0.001: active_rules.append("法則5(チャンス)")
            
        return {
            "現在値": f"{now_p:,.1f}",
            "MA60乖離": f"{((now_p/m60)-1)*100:.2f}%",
            "MA200乖離": f"{((now_p/m200)-1)*100:.2f}%",
            "検知状況": " / ".join(active_rules) if active_rules else "監視中（静観）"
        }
    except:
        return {"現在値": "取得不可", "MA60乖離": "-", "MA200乖離": "-", "検知状況": "停止中"}

# --- サイドバー：コントロールパネル ---
st.sidebar.title("🎮 操作パネル")
if st.sidebar.button("🔍 今すぐ全市場スキャンを予約", use_container_width=True):
    st.sidebar.info("GitHub Actionsでスキャンを開始してください。完了すると下のリストが更新されます。")

# --- メイン画面：監視状況の可視化 ---
st.title("📊 リアルタイム監視ダッシュボード")
if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    
    if watchlist:
        monitor_data = []
        for item in watchlist:
            stat = get_status(item['ticker'])
            monitor_data.append({
                "銘柄": item.get('name', item['ticker']),
                "コード": item['ticker'],
                "現在値": stat["現在値"],
                "MA60乖離": stat["MA60乖離"],
                "MA200乖離": stat["MA200乖離"],
                "状況": stat["検知状況"]
            })
        st.table(pd.DataFrame(monitor_data))
    else:
        st.write("現在、監視中の銘柄はありません。")
else:
    st.write("監視リストが空です。")

st.divider()

# --- スキャン結果と登録 ---
st.header("✨ スキャン結果からの登録")
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.caption(f"最終スキャン：{data['date']}")
    
    hits = data['hits']
    selected = []
    cols = st.columns(3)
    for i, (t, info) in enumerate(hits.items()):
        with cols[i % 3]:
            name = info.get('name', t)
            if st.checkbox(f"**{name}** ({t})\n{info.get('reason','')}", key=f"check_{t}"):
                selected.append({"ticker": t, "name": name})
    
    if st.button("🚀 選択した銘柄を監視リストに登録", type="primary"):
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(selected, f, ensure_ascii=False, indent=2)
        st.success(f"{len(selected)} 銘柄の監視を開始しました！")
        st.balloons()
