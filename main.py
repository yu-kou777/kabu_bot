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

st.set_page_config(page_title="Jack株AI：完全安定版", layout="centered")

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

# --- 手動での指標計算ロジック ---
def calculate_indicators(df):
    # MA
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['MA200'] = df['Close'].rolling(window=200).mean()
    # BB (20)
    ma20 = df['Close'].rolling(window=20).mean()
    std20 = df['Close'].rolling(window=20).std()
    df['BB_u2'] = ma20 + (std20 * 2)
    df['BB_l3'] = ma20 - (std20 * 3)
    # RSI (14)
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
        rsi_txt = f"(RSI:{last['RSI']:.1f})"
        
        # 法則判定
        if last['RSI'] <= 10 or last['RSI'] >= 80: sigs.append(f"🚨【RSI警告】{rsi_txt}")
        if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_u2'].tail(10)).sum() >= 3:
            sigs.append("法則1:BB+2σx3(売)")
        if last['Close'] < last['MA60'] and last['Low'] <= last['BB_l3']:
            sigs.append("🔥法則4:BB-3σ接触(買)")
        if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
            sigs.append("💎法則6:60MA反発(売)")
            
        for s in sigs: send_discord(f"🔔 **{ticker}**\n{s} {rsi_txt}")
        return sigs
    except: return []

# --- UI メイン ---
tab1, tab2 = st.tabs(["⚙️ 設定", "☀️ 精密監視パネル"])

with tab1:
    st.subheader("監視銘柄の登録")
    selected = st.multiselect("銘柄選択", list(JPX400_DICT.keys()))
    if st.button("✅ 保存してスタート"):
        data = [{"ticker": t, "added_date": get_jst_now().strftime('%Y-%m-%d')} for t in selected]
        with open(WATCHLIST_FILE, 'w') as f: json.dump(data, f)
        st.success("リストを更新しました。")

with tab2:
    jst_now = get_jst_now()
    st.write(f"🕰 **日本時間: {jst_now.strftime('%H:%M:%S')}**")
    watch_data = load_watchlist()
    
    if st.button("🔴 強制停止", type="primary"):
        st.session_state.manual_stop = True
        st.rerun()

    if not st.session_state.get('manual_stop'):
        now_time = jst_now.time()
        is_trading = (dt_time(9, 20) <= now_time <= dt_time(11, 50)) or (dt_time(12, 50) <= now_time <= dt_time(15, 20))
        
        if is_trading and watch_data:
            placeholder = st.empty()
            for item in watch_data: check_logic(item['ticker'])
            for i in range(300, 0, -1):
                placeholder.success(f"🚀 5分サイクルで監視中... \n\n ⏳ 次まで: **{i}秒**")
                time.sleep(1)
            st.rerun()
        else:
            st.info(f"🕒 現在は待機中です。(日本時間: {jst_now.strftime('%H:%M:%S')})")
            time.sleep(60); st.rerun()
    else:
        if st.button("▶️ 再開"):
            del st.session_state.manual_stop; st.rerun()

