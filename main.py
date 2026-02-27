import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, time as dt_time, timedelta, timezone
import time
import numpy as np

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：操作パネル", layout="centered")

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f: return json.load(f)
        except: return []
    return []

# --- UI メイン ---
tab1, tab2 = st.tabs(["🌙 銘柄を探す・登録", "☀️ リアルタイム監視状況"])

with tab1:
    st.header("監視銘柄の登録")
    
    # RSIスキャン
    rsi_threshold = st.slider("スキャンするRSIのしきい値", 10, 80, 40)
    
    if st.button("全銘柄から条件に合う銘柄を探す"):
        found = []
        bar = st.progress(0)
        tickers = list(JPX400_DICT.keys())
        # 【修正】RSI計算のために期間を1ヶ月(1mo)に延長
        all_data = yf.download(tickers, period="1mo", interval="1d", group_by='ticker', progress=False)
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers))
            try:
                df_d = all_data[t].dropna()
                if len(df_d) < 14: continue
                delta = df_d['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rsi_s = 100 - (100 / (1 + (gain / loss)))
                last_rsi = rsi_s.iloc[-1]
                if last_rsi <= rsi_threshold:
                    found.append(f"{t} {JPX400_DICT.get(t)}")
            except: continue
        st.session_state.found_list = found

    st.write("---")
    options = [f"{code} {name}" for code, name in JPX400_DICT.items()]
    
    # 検索で見つかったものをデフォルトで選択状態にする
    default_vals = st.session_state.get('found_list', [])
    if default_vals:
        st.info(f"条件に合う銘柄が {len(default_vals)} 件見つかりました。そのまま保存できます。")

    selected_full = st.multiselect("監視リストに追加する銘柄を選択", options, default=default_vals)
    
    if st.button("✅ 監視リストを保存して開始"):
        if selected_full:
            selected_codes = [x.split(" ")[0] for x in selected_full]
            data = [{"ticker": t, "added_date": get_jst_now().strftime('%Y-%m-%d')} for t in selected_codes]
            with open(WATCHLIST_FILE, 'w') as f: json.dump(data, f)
            st.success(f"{len(selected_codes)} 銘柄を保存しました！")
            send_discord(f"▶️ 【システム】監視銘柄を更新しました（{len(selected_codes)}銘柄）")
        else:
            st.error("銘柄が選択されていません。")

with tab2:
    jst_now = get_jst_now()
    st.subheader(f"🕰 現在時刻: {jst_now.strftime('%H:%M:%S')}")
    watch_data = load_watchlist()
    
    if watch_data:
        st.info(f"現在 {len(watch_data)} 銘柄を裏側で自動監視しています。")
        with st.expander("📋 監視中の銘柄リスト", expanded=True):
            for item in watch_data:
                st.write(f"・{item['ticker']} {JPX400_DICT.get(item['ticker'])}")
        
        # 強制停止ボタン
        if st.button("🔴 監視を完全に停止する", type="primary"):
            st.session_state.manual_stop = True
            send_discord("🛑 【システム】友幸さんにより監視が強制停止されました。")
            st.rerun()
    else:
        st.warning("監視リストが空です。「銘柄を探す」タブで銘柄を選んで保存してください。")
