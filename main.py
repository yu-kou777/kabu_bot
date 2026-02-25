import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import json
import os
import datetime

# ==========================================
# ⚙️ 設定（Jackさんの最新Webhook）
# ==========================================
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
# 日経400銘柄の例（ここに必要な銘柄コードを追加してください）
TICKERS = ["5713.T", "6330.T", "7203.T", "9984.T", "8035.T", "6758.T", "9101.T"]

st.set_page_config(page_title="Jack株AI監視", layout="wide")

# ==========================================
# 🧠 6つの法則判定ロジック
# ==========================================
def judge_signals(df, ticker):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []
    
    # 法則1: 60MA上 & BB+2σに3回接触
    touch_count = (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum()
    if last['Close'] > last['MA60'] and touch_count >= 3:
        signals.append("法則1: 強気圏限界(売り)")
        
    # 法則2: 60MA上 & 60MA接触で(反発)買い / 割ったら売り
    if last['Close'] > last['MA60']:
        if last['Low'] <= last['MA60']: signals.append("法則2: 60MA反発(買い)")
        if last['Close'] < last['MA60']: signals.append("法則2: 60MA割れ(売り)")

    # 法則3: 200MA > 60MAの時、200MA接触で売り
    if last['MA200'] > last['MA60'] and last['High'] >= last['MA200']:
        signals.append("法則3: 200MA壁(売り)")

    # 法則4: 60MA下 & BB-3σ接触で買い
    if last['Close'] < last['MA60'] and last['Low'] <= last['BB_low_3']:
        signals.append("法則4: 極限売られすぎBB-3(買い)")

    # 法則5: 60MA下 & 200MA接触で(反発)買い / 割ったら売り
    if last['Close'] < last['MA60']:
        if last['Low'] <= last['MA200']: signals.append("法則5: 200MA反発(買い)")
        if last['Close'] < last['MA200']: signals.append("法則5: 200MA割れ(売り)")

    # 法則6: 60MA下 & 60MA接触で(反発)売り / 越えたら買い
    if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
        signals.append("法則6: 60MA反発(売り)")
    if last['Close'] > last['MA60'] and prev['Close'] < prev['MA60']:
        signals.append("法則6: 60MA突破(買い)")

    return signals

# ==========================================
# 📱 画面表示用 (垂直並び)
# ==========================================
def draw_card(ticker, df):
    last = df.iloc[-1]
    # MA未来予測：今の価格が60本前より高ければ上昇
    trend = "⤴️ 上昇" if last['Close'] > df['Close'].shift(60).iloc[-1] else "⤵️ 下降"
    color = "red" if "上昇" in trend else "blue"
    
    with st.expander(f"【{ticker}】 {trend}", expanded=True):
        st.markdown(f"**状態:** <span style='color:{color}'>{trend}</span>", unsafe_allow_html=True)
        st.write(f"📈 **ボリンジャー上値(+2σ)**: {last['BB_up_2']:,.1f}")
        st.write(f"💰 **現在値**: {last['Close']:,.1f}")
        st.write(f"🟦 **MA60 (1時間線)**: {last['MA60']:,.1f}")
        st.write(f"⬜ **MA200 (中期線)**: {last['MA200']:,.1f}")
        st.write(f"📉 **ボリンジャー下値(-3σ)**: {last['BB_low_3']:,.1f}")
        if st.button(f"この銘柄を削除", key=f"del_{ticker}"):
            return True
    return False

# ==========================================
# 🚀 メイン動作
# ==========================================
mode = st.sidebar.radio("モード選択", ["1.夜の選別", "2.昼の自動監視"])

if mode == "1.夜の選別":
    st.header("🌙 夜のスクリーニング (日足RSI 20以下)")
    if st.button("チャンス銘柄を抽出"):
        found = []
        for t in TICKERS:
            d_df = yf.download(t, period="20d", interval="1d", progress=False)
            rsi = ta.rsi(d_df['Close'], length=14).iloc[-1]
            if rsi <= 20: found.append(t)
        st.session_state.temp_list = found
    
    if 'temp_list' in st.session_state:
        final_list = []
        for t in st.session_state.temp_list:
            df = yf.download(t, period="2d", interval="1m", progress=False)
            # 指標計算
            df['MA60'] = ta.sma(df['Close'], length=60)
            df['MA200'] = ta.sma(df['Close'], length=200)
            df['BB_up_2'] = ta.bbands(df['Close'], length=20, std=2)['BBU_20_2.0']
            df['BB_low_3'] = ta.bbands(df['Close'], length=20, std=3)['BBL_20_3.0']
            
            if not draw_card(t, df): final_list.append(t)
        
        if st.button("選定銘柄を保存して監視予約"):
            with open(WATCHLIST_FILE, 'w') as f:
                json.dump(final_list, f)
            st.success("保存完了！")

elif mode == "2.昼 of 昼の自動監視":
    st.header("☀️ 本日の自動監視リスト")
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f:
            watchlist = json.load(f)
        
        for t in watchlist:
            df = yf.download(t, period="1d", interval="1m", progress=False)
            # ※指標計算（省略：上記と同じ）
            signals = judge_signals(df, t)
            if signals:
                msg = f"🔔 **{t}**\nシグナル: {', '.join(signals)}"
                requests.post(DISCORD_URL, json={"content": msg})
                st.toast(msg)
