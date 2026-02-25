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

# JPX400の主要銘柄。全400を直接書くと制限に触れるため、主要セクターを網羅。
# ※さらに追加したい場合は、'数字4桁.T' の形式でカンマ区切りで追加してください。
JPX400_ALL = [
    '1605.T', '1801.T', '1802.T', '1812.T', '1925.T', '1928.T', '2502.T', '2503.T', '2802.T', '2914.T',
    '3402.T', '3407.T', '4063.T', '4188.T', '4452.T', '4502.T', '4503.T', '4507.T', '4519.T', '4523.T',
    '4568.T', '4661.T', '4901.T', '4911.T', '5020.T', '5108.T', '5401.T', '5406.T', '5411.T', '5713.T',
    '5802.T', '6098.T', '6178.T', '6273.T', '6301.T', '6326.T', '6367.T', '6501.T', '6503.T', '6594.T',
    '6645.T', '6701.T', '6702.T', '6723.T', '6752.T', '6758.T', '6857.T', '6861.T', '6902.T', '6920.T',
    '6954.T', '6971.T', '6981.T', '7011.T', '7201.T', '7203.T', '7267.T', '7269.T', '7309.T', '7733.T',
    '7741.T', '7751.T', '7832.T', '7974.T', '8001.T', '8002.T', '8031.T', '8035.T', '8053.T', '8058.T',
    '8113.T', '8267.T', '8306.T', '8316.T', '8411.T', '8591.T', '8604.T', '8630.T', '8725.T', '8750.T',
    '8766.T', '8801.T', '8802.T', '8830.T', '9020.T', '9021.T', '9022.T', '9101.T', '9104.T', '9107.T',
    '9201.T', '9202.T', '9432.T', '9433.T', '9434.T', '9501.T', '9502.T', '9503.T', '9613.T', '9735.T',
    '9843.T', '9983.T', '9984.T'
]

st.set_page_config(page_title="Jack株AI", layout="centered")

# --- データ取得 ---
def get_stock_data(ticker, period="5d", interval="1m"):
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
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

# --- 判定ロジック ---
def judge_jack_laws(df, ticker):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    sigs = []
    if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
        sigs.append("法則1: 強気限界(売)")
    if last['Close'] > last['MA60']:
        if last['Low'] <= last['MA60']: sigs.append("法則2: 60MA反発(買)")
        if last['Close'] < last['MA60']: sigs.append("法則2: 60MA割れ(売)")
    if last['MA200'] > last['MA60'] and last['High'] >= last['MA200']:
        sigs.append("法則3: 200MA抵抗(売)")
    if last['Close'] < last['MA60'] and last['Low'] <= last['BB_low_3']:
        sigs.append("法則4: BB-3σ反発(買)")
    if last['Close'] < last['MA60']:
        if last['Low'] <= last['MA200']: sigs.append("法則5: 200MA反発(買)")
        if last['Close'] < last['MA200']: sigs.append("法則5: 200MA割れ(売)")
    if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
        sigs.append("法則6: 60MA反発(売)")
    if last['Close'] > last['MA60'] and prev['Close'] < prev['MA60']:
        sigs.append("法則6: 60MA突破(買)")
    return sigs

# --- UI ---
st.title("📈 Jack株AI：選別と監視")
tab1, tab2 = st.tabs(["🌙 夜の選別(RSI)", "☀️ 昼の監視"])

with tab1:
    st.subheader("日足RSIによるスクリーニング")
    rsi_threshold = st.slider("RSIしきい値(以下を抽出)", 10, 40, 30)
    
    if st.button("全銘柄スキャン開始"):
        found = []
        progress_bar = st.progress(0)
        for i, t in enumerate(JPX400_ALL):
            progress_bar.progress((i + 1) / len(JPX400_ALL))
            d_df = yf.download(t, period="20d", interval="1d", progress=False)
            if d_df.empty: continue
            rsi = ta.rsi(d_df['Close'], length=14).iloc[-1]
            if rsi <= rsi_threshold:
                found.append({"ticker": t, "rsi": rsi})
        st.session_state.found = found
    
    if 'found' in st.session_state:
        final_list = []
        for item in st.session_state.found:
            t = item['ticker']
            r = item['rsi']
            
            # RSIレベルによる差別化
            if r <= 20:
                header_text = f"🔥【超チャンス】{t} (RSI: {r:.1f})"
                bg_color = "#FFCCCC" # 濃い赤
            else:
                header_text = f"✅【注目】{t} (RSI: {r:.1f})"
                bg_color = "#E6F3FF" # 薄い青
            
            with st.container():
                st.markdown(f"<div style='background-color:{bg_color}; padding:10px; border-radius:5px;'>", unsafe_allow_html=True)
                df = get_stock_data(t)
                if df is not None:
                    last = df.iloc[-1]
                    st.write(f"### {header_text}")
                    st.write(f"🔴 BB+2σ: {last['BB_up_2']:,.1f} | 💰 現在値: {last['Close']:,.1f}")
                    st.write(f"🔵 MA60 : {last['MA60']:,.1f} | ⚪ MA200: {last['MA200']:,.1f}")
                    st.write(f"🟢 BB-3σ: {last['BB_low_3']:,.1f}")
                    if st.checkbox(f"監視に追加: {t}", value=True, key=f"check_{t}"):
                        final_list.append(t)
                st.markdown("</div>", unsafe_allow_html=True)
                st.write("---")
        
        if st.button("選定銘柄を監視リストへ保存"):
            with open(WATCHLIST_FILE, 'w') as f: json.dump(final_list, f)
            st.success(f"{len(final_list)}銘柄を保存しました。昼の監視タブに移動してください。")

with tab2:
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f: watchlist = json.load(f)
        st.write(f"監視対象: {', '.join(watchlist)}")
        if st.button("監視スタート(スマホはこのまま放置)"):
            status_area = st.empty()
            while True:
                for t in watchlist:
                    status_area.text(f"監視中: {t} ({datetime.now().strftime('%H:%M:%S')})")
                    df = get_stock_data(t)
                    if df is not None:
                        sigs = judge_jack_laws(df, t)
                        if sigs:
                            requests.post(DISCORD_URL, json={"content": f"🔔 {t} 【シグナル検知】\n{', '.join(sigs)}"})
                            st.toast(f"{t} 検知！")
