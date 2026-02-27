import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
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

st.set_page_config(page_title="Jack株AI：5分同期・精密監視版", layout="centered")

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

# --- 判定ロジック：RSI 10/80 & 7つの法則 ---
def check_logic(ticker):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if len(df) < 60: return []
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['MA60'] = ta.sma(df['Close'], length=60)
        df['MA200'] = ta.sma(df['Close'], length=200)
        df['MA60_s'] = df['MA60'].diff()
        df['MA200_s'] = df['MA200'].diff()
        bb2 = ta.bbands(df['Close'], length=20, std=2)
        bb3 = ta.bbands(df['Close'], length=20, std=3)
        df['BB_u2'] = bb2['BBU_20_2.0']; df['BB_l3'] = bb3['BBL_20_3.0']

        last = df.iloc[-1]; sigs = []
        rsi_txt = f"(RSI:{last['RSI']:.1f})"
        is_strong_trend = (last['MA60_s'] * last['MA200_s'] > 0) # 傾きが同じ向き

        # RSI極限
        if last['RSI'] <= 10 or last['RSI'] >= 80: sigs.append(f"🚨【RSI警告】{rsi_txt}")
        # 法則判定
        if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_u2'].tail(10)).sum() >= 3:
            sigs.append(f"法則1:BB+2σx3(売)")
        if last['Close'] < last['MA60'] and last['Low'] <= last['BB_l3']:
            sigs.append(f"🔥法則4:BB-3σ接触(買)")
        if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
            sigs.append(f"💎法則6:60MA反発(売)")

        for s in sigs:
            prefix = "💎【超王道】" if is_strong_trend else "🔔"
            send_discord(f"{prefix} **{ticker}**\n{s} {rsi_txt}")
        return sigs
    except: return []

# --- UI メイン ---
tab1, tab2 = st.tabs(["⚙️ 設定", "☀️ 5分精密監視パネル"])

with tab1:
    st.subheader("監視銘柄の登録")
    selected_tickers = st.multiselect("銘柄を選択してください", list(JPX400_DICT.keys()))
    if st.button("✅ リストを更新してスタート"):
        data = [{"ticker": t, "added_date": get_jst_now().strftime('%Y-%m-%d')} for t in selected_tickers]
        with open(WATCHLIST_FILE, 'w') as f: json.dump(data, f)
        st.success("リストを更新しました。監視タブを確認してください。")

with tab2:
    jst_now = get_jst_now()
    now_time = jst_now.time()
    st.write(f"🕰 **日本時間: {jst_now.strftime('%H:%M:%S')}**")
    
    watch_data = load_watchlist()
    if st.button("🔴 強制停止", type="primary"):
        st.session_state.manual_stop = True
        st.rerun()

    if not st.session_state.get('manual_stop'):
        is_trading = (dt_time(9, 20) <= now_time <= dt_time(11, 50)) or (dt_time(12, 50) <= now_time <= dt_time(15, 20))
        
        if is_trading and watch_data:
            placeholder = st.empty()
            # 全銘柄をスキャン
            for item in watch_data:
                check_logic(item['ticker'])
            
            # --- 裏監視(5分)に合わせた300秒のカウントダウン ---
            for i in range(300, 0, -1):
                placeholder.success(f"🚀 5分サイクルで精密監視中... \n\n ⏳ 次のスキャンまで: **{i}秒**")
                time.sleep(1)
            st.rerun()
        else:
            st.info("🕒 取引時間外または待機中です。")
            time.sleep(60); st.rerun()
    else:
        st.warning("強制停止中")
        if st.button("▶️ 再開"):
            del st.session_state.manual_stop; st.rerun()
