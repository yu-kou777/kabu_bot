import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import json
import os
from datetime import datetime

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_SAMPLE = ["5713.T", "6330.T", "7203.T", "9984.T", "8035.T", "9101.T"]

st.set_page_config(page_title="Jack株AI", layout="centered")

# --- 計算・判定ロジック ---
def get_stock_data(ticker):
    try:
        df = yf.download(ticker, period="5d", interval="1m", progress=False)
        if df.empty: return None
        df['MA60'] = ta.sma(df['Close'], length=60)
        df['MA200'] = ta.sma(df['Close'], length=200)
        bb = ta.bbands(df['Close'], length=20, std=2)
        df['BB_up_2'] = bb['BBU_20_2.0']
        bb3 = ta.bbands(df['Close'], length=20, std=3)
        df['BB_low_3'] = bb3['BBL_20_3.0']
        return df
    except:
        return None

def judge_jack_laws(df, ticker):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    sigs = []
    # 法則1: 60MA上 & BB+2σ 3回接触
    if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
        sigs.append("法則1: 強気限界(売)")
    # 法則2: 60MA上
    if last['Close'] > last['MA60']:
        if last['Low'] <= last['MA60']: sigs.append("法則2: 60MA反発(買)")
        if last['Close'] < last['MA60']: sigs.append("法則2: 60MA割れ(売)")
    # 法則3: 200MA壁
    if last['MA200'] > last['MA60'] and last['High'] >= last['MA200']:
        sigs.append("法則3: 200MA抵抗(売)")
    # 法則4: BB-3σ反発(買)
    if last['Close'] < last['MA60'] and last['Low'] <= last['BB_low_3']:
        sigs.append("法則4: BB-3σ反発(買)")
    # 法則5: 200MA反発(買)
    if last['Close'] < last['MA60']:
        if last['Low'] <= last['MA200']: sigs.append("法則5: 200MA反発(買)")
        if last['Close'] < last['MA200']: sigs.append("法則5: 200MA割れ(売)")
    # 法則6: 60MA突破(買)
    if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
        sigs.append("法則6: 60MA反発(売)")
    if last['Close'] > last['MA60'] and prev['Close'] < prev['MA60']:
        sigs.append("法則6: 60MA突破(買)")
    return sigs

# --- UI ---
st.title("📈 Jack株AI監視")
tab1, tab2 = st.tabs(["🌙 夜の選別", "☀️ 昼の監視"])

with tab1:
    if st.button("チャンス銘柄を抽出"):
        st.session_state.found = JPX400_SAMPLE
    if 'found' in st.session_state:
        final = []
        for t in st.session_state.found:
            df = get_stock_data(t)
            if df is not None:
                last = df.iloc[-1]
                # 垂直並び
                with st.expander(f"【{t}】 表示", expanded=True):
                    st.write(f"🔴 BB+2σ: {last['BB_up_2']:,.0f}")
                    st.write(f"💰 現在値: {last['Close']:,.0f}")
                    st.write(f"🔵 MA60 : {last['MA60']:,.0f}")
                    st.write(f"⚪ MA200: {last['MA200']:,.0f}")
                    st.write(f"🟢 BB-3σ: {last['BB_low_3']:,.0f}")
                    if st.checkbox(f"監視に含める: {t}", value=True): final.append(t)
        if st.button("選定銘柄を保存"):
            with open(WATCHLIST_FILE, 'w') as f: json.dump(final, f)
            st.success("保存完了")

with tab2:
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f: watchlist = json.load(f)
        st.write(f"{len(watchlist)} 銘柄を監視中...")
        if st.button("監視スタート"):
            for t in watchlist:
                df = get_stock_data(t)
                if df is not None:
                    sigs = judge_jack_laws(df, t)
                    if sigs:
                        requests.post(DISCORD_URL, json={"content": f"🔔 {t}: {sigs}"})
                        st.toast(f"{t} 検知！")
