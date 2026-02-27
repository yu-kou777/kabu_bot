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

st.set_page_config(page_title="Jack株AI：5日RSIスキャナー", layout="wide")

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- UI：操作タブ ---
tab1, tab2 = st.tabs(["🌙 5日間RSIスキャン・登録", "☀️ 監視中の銘柄状況"])

with tab1:
    st.header("🌙 直近5日間の動きから銘柄を抽出")
    if 'temp_watchlist' not in st.session_state: st.session_state.temp_watchlist = {}
    if 'scan_results' not in st.session_state: st.session_state.scan_results = []

    st.subheader("🔍 RSIスキャン条件設定")
    col1, col2 = st.columns(2)
    with col1:
        threshold = st.slider("RSIしきい値（この数値以下を検知）", 10, 60, 40)
    with col2:
        st.write("直近5日間の日足データのうち、一度でもしきい値を下回った銘柄を表示します。")

    if st.button("🚀 JPX400全銘柄スキャン開始"):
        st.session_state.scan_results = []
        tickers = list(JPX400_DICT.keys())
        # RSI計算のため少し長めにデータを取得
        data = yf.download(tickers, period="2mo", interval="1d", group_by='ticker', progress=False)
        
        for t in tickers:
            try:
                df = data[t].dropna()
                if len(df) < 20: continue
                rsi_series = calculate_rsi(df)
                # 直近5日間の最小RSIを取得
                recent_min_rsi = rsi_series.tail(5).min()
                current_rsi = rsi_series.iloc[-1]
                
                if recent_min_rsi <= threshold:
                    st.session_state.temp_watchlist[t] = f"直近5日RSI低迷({recent_min_rsi:.1f})"
                    st.session_state.scan_results.append({
                        "コード": t,
                        "和名": JPX400_DICT[t],
                        "5日内最小RSI": round(recent_min_rsi, 1),
                        "現在RSI": round(current_rsi, 1)
                    })
            except: continue
        
        if st.session_state.scan_results:
            st.success(f"{len(st.session_state.scan_results)}銘柄が見つかりました！")
            st.table(pd.DataFrame(st.session_state.scan_results))
        else:
            st.warning("条件に合う銘柄はありませんでした。しきい値を上げて試してください。")

    st.write("---")
    options = [f"{c} {n}" for c, n in JPX400_DICT.items()]
    current_hits = [f"{t} {JPX400_DICT[t]}" for t in st.session_state.temp_watchlist.keys()]
    selected_full = st.multiselect("監視リストに追加する銘柄を選択", options, default=current_hits)
    
    if st.button("💾 監視リストを保存"):
        final_list = []
        for full in selected_full:
            ticker = full.split(" ")[0]
            reason = st.session_state.temp_watchlist.get(ticker, "手動追加")
            final_list.append({"ticker": ticker, "name": JPX400_DICT[ticker], "reason": reason, "at": get_jst_now().strftime('%m/%d %H:%M')})
        with open(WATCHLIST_FILE, 'w') as f: json.dump(final_list, f)
        st.success("保存完了！")
        st.session_state.temp_watchlist = {}

with tab2:
    st.header("☀️ 現在の監視リスト")
    if st.button("🗑️ 全削除", type="primary"):
        with open(WATCHLIST_FILE, 'w') as f: json.dump([], f)
        st.rerun()
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f:
            for item in json.load(f):
                st.write(f"🔵 **{item['ticker']} {item['name']}** ({item['reason']})")
