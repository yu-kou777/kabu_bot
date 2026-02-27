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

st.set_page_config(page_title="Jack株AI：完全版", layout="centered")

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

# --- 指標計算 ---
def calculate_indicators(df):
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['MA200'] = df['Close'].rolling(window=200).mean()
    # ボリンジャーバンド
    ma20 = df['Close'].rolling(window=20).mean()
    std20 = df['Close'].rolling(window=20).std()
    df['BB_u2'] = ma20 + (std20 * 2)
    df['BB_l3'] = ma20 - (std20 * 3)
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))
    return df

def check_logic(ticker):
    try:
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        if len(df) < 200: return []
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = calculate_indicators(df)
        last = df.iloc[-1]; sigs = []
        name = JPX400_DICT.get(ticker, "")
        rsi_txt = f"(RSI:{last['RSI']:.1f})"
        
        # 法則判定
        if last['RSI'] <= 10 or last['RSI'] >= 80: sigs.append(f"🚨【RSI警告】{rsi_txt}")
        if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_u2'].tail(10)).sum() >= 3:
            sigs.append("法則1:BB+2σx3(売)")
        if last['Low'] <= last['BB_l3']: sigs.append("🔥法則4:BB-3σ接触(買)")
            
        for s in sigs: send_discord(f"🔔 **{ticker} {name}**\n{s} {rsi_txt}")
        return sigs
    except: return []

# --- UI メイン ---
tab1, tab2 = st.tabs(["🌙 夜の選別・登録", "☀️ リアルタイム監視"])

with tab1:
    st.header("監視する銘柄を選んでください")
    
    # RSIスキャン設定
    rsi_threshold = st.slider("スキャンするRSIのしきい値", 10, 60, 40)
    
    if st.button("全銘柄からRSI条件に合う銘柄を探す"):
        found = []
        bar = st.progress(0)
        tickers = list(JPX400_DICT.keys())
        all_data = yf.download(tickers, period="5d", interval="1d", group_by='ticker', progress=False)
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers))
            try:
                df_d = all_data[t].dropna()
                delta = df_d['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rsi_s = 100 - (100 / (1 + (gain / loss)))
                min_rsi = rsi_s.tail(3).min()
                if min_rsi <= rsi_threshold: found.append({"ticker": t, "mr": min_rsi})
            except: continue
        st.session_state.found = found

    # 検索結果または直接選択からの登録
    st.write("---")
    options = [f"{code} {name}" for code, name in JPX400_DICT.items()]
    
    # 検索で見つかったものをデフォルト選択にする
    default_selection = []
    if 'found' in st.session_state:
        default_selection = [f"{f['ticker']} {JPX400_DICT.get(f['ticker'])}" for f in st.session_state.found]
        st.write(f"条件に合う銘柄が {len(default_selection)} 件見つかりました。")

    selected_full = st.multiselect("監視リストに追加する銘柄を選択", options, default=default_selection)
    
    if st.button("✅ 監視リストを保存して開始"):
        if selected_full:
            selected_codes = [x.split(" ")[0] for x in selected_full]
            data = [{"ticker": t, "added_date": get_jst_now().strftime('%Y-%m-%d')} for t in selected_codes]
            with open(WATCHLIST_FILE, 'w') as f: json.dump(data, f)
            st.success(f"{len(selected_codes)} 銘柄を保存しました！「リアルタイム監視」タブへ移動してください。")
            send_discord(f"▶️ 【システム】監視銘柄を更新しました（{len(selected_codes)}銘柄）")
        else:
            st.error("銘柄が選択されていません。")

with tab2:
    jst_now = get_jst_now()
    st.subheader(f"🕰 現在時刻: {jst_now.strftime('%H:%M:%S')}")
    watch_data = load_watchlist()
    
    if st.button("🔴 監視を完全に停止する", type="primary"):
        st.session_state.manual_stop = True
        st.rerun()

    if not st.session_state.get('manual_stop'):
        if watch_data:
            with st.expander("📋 現在の監視リストを表示中", expanded=True):
                for item in watch_data:
                    st.write(f"・{item['ticker']} {JPX400_DICT.get(item['ticker'])}")
            
            now_time = jst_now.time()
            is_trading = (dt_time(9, 20) <= now_time <= dt_time(11, 50)) or (dt_time(12, 50) <= now_time <= dt_time(15, 20))
            
            if is_trading:
                placeholder = st.empty()
                for item in watch_data: check_logic(item['ticker'])
                for i in range(300, 0, -1):
                    placeholder.success(f"🚀 精密監視中... \n\n ⏳ 次まで: **{i}秒**")
                    time.sleep(1)
                st.rerun()
            else:
                st.info("🕒 取引時間外です。")
                time.sleep(60); st.rerun()
        else:
            st.warning("監視リストが空です。「夜の選別・登録」タブで銘柄を選んで保存してください。")
    else:
        if st.button("▶️ 監視を再開する"):
            del st.session_state.manual_stop; st.rerun()
