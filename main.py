import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import json
import os
from datetime import datetime, time as dt_time
import time

# ==========================================
# ⚙️ 設定
# ==========================================
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"

# 主要な日経400銘柄（スキャン対象）
JPX400_ALL = [
    '1605.T', '1801.T', '1802.T', '1812.T', '1925.T', '1928.T', '2502.T', '2503.T', '2802.T', '2914.T',
    '3402.T', '3407.T', '4063.T', '4188.T', '4452.T', '4502.T', '4503.T', '4507.T', '4519.T', '4523.T',
    '4568.T', '4661.T', '4901.T', '4911.T', '5020.T', '5108.T', '5401.T', '5406.T', '5411.T', '5713.T',
    '5802.T', '6098.T', '6178.T', '6273.T', '6301.T', '6326.T', '6330.T', '6367.T', '6501.T', '6503.T',
    '6594.T', '6645.T', '6701.T', '6702.T', '6723.T', '6752.T', '6758.T', '6857.T', '6861.T', '6902.T',
    '6920.T', '6954.T', '6971.T', '6981.T', '7011.T', '7201.T', '7203.T', '7267.T', '7269.T', '7309.T',
    '7733.T', '7741.T', '7751.T', '7832.T', '7974.T', '8001.T', '8002.T', '8031.T', '8035.T', '8053.T',
    '8058.T', '8113.T', '8267.T', '8306.T', '8316.T', '8411.T', '8591.T', '8604.T', '8630.T', '8725.T',
    '8750.T', '8766.T', '8801.T', '8802.T', '8830.T', '9020.T', '9021.T', '9022.T', '9101.T', '9104.T',
    '9107.T', '9201.T', '9202.T', '9432.T', '9433.T', '9434.T', '9501.T', '9502.T', '9503.T', '9613.T',
    '9735.T', '9843.T', '9983.T', '9984.T'
]

st.set_page_config(page_title="Jack株AI監視", layout="centered")

# --- 保存・読み込み機能 ---
def save_watchlist(tickers):
    with open(WATCHLIST_FILE, 'w') as f:
        json.dump(tickers, f)

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f:
            return json.load(f)
    return []

# --- データ取得・判定（Jackの6つの法則） ---
def get_stock_data(ticker):
    try:
        df = yf.download(ticker, period="5d", interval="1m", progress=False)
        if df.empty: return None
        df['MA60'] = ta.sma(df['Close'], length=60)
        df['MA200'] = ta.sma(df['Close'], length=200)
        bb2 = ta.bbands(df['Close'], length=20, std=2)
        df['BB_up_2'] = bb2['BBU_20_2.0']
        bb3 = ta.bbands(df['Close'], length=20, std=3)
        df['BB_low_3'] = bb3['BBL_20_3.0']
        return df
    except: return None

def judge_jack_laws(df, ticker):
    last = df.iloc[-1]; prev = df.iloc[-2]; sigs = []
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

# ==========================================
# 📱 UI
# ==========================================
st.title("📉 Jack株AI：選別と3分監視")

# 監視銘柄の記憶を読み込み
current_watchlist = load_watchlist()

tab1, tab2 = st.tabs(["🌙 夜の選別", "☀️ 3分刻み監視"])

with tab1:
    st.subheader("日足RSIスクリーニング")
    rsi_val = st.slider("抽出するRSI（30以下推奨）", 10, 40, 30)
    
    col1, col2 = st.columns(2)
    if col1.button("全銘柄スキャン開始"):
        found = []
        bar = st.progress(0)
        for i, t in enumerate(JPX400_ALL):
            bar.progress((i + 1) / len(JPX400_ALL))
            d_df = yf.download(t, period="20d", interval="1d", progress=False)
            if d_df.empty: continue
            rsi = ta.rsi(d_df['Close'], length=14).iloc[-1]
            if rsi <= rsi_val:
                found.append({"ticker": t, "rsi": rsi})
        st.session_state.found = found
    
    if col2.button("監視リストをリセット"):
        save_watchlist([])
        st.rerun()

    if 'found' in st.session_state:
        st.write(f"### {len(st.session_state.found)} 件見つかりました")
        selected = []
        for item in st.session_state.found:
            t, r = item['ticker'], item['rsi']
            color = "#FFCCCC" if r <= 20 else "#E6F3FF"
            with st.container():
                st.markdown(f"<div style='background-color:{color}; padding:10px; border-radius:5px;'>", unsafe_allow_html=True)
                st.write(f"**{t}** (RSI: {r:.1f})")
                if st.checkbox(f"監視に登録", value=True, key=f"sel_{t}"):
                    selected.append(t)
                st.markdown("</div>", unsafe_allow_html=True)
        
        if st.button("この銘柄で監視を開始する"):
            save_watchlist(selected)
            st.success("保存しました！「昼の監視」タブでスタートしてください。")

with tab2:
    if not current_watchlist:
        st.warning("監視銘柄が登録されていません。夜の選別タブで登録してください。")
    else:
        st.write(f"📋 現在の監視銘柄: {', '.join(current_watchlist)}")
        if st.button("3分刻み監視スタート"):
            placeholder = st.empty()
            while True:
                now = datetime.now().time()
                if dt_time(9, 20) <= now <= dt_time(15, 20):
                    now_str = datetime.now().strftime('%H:%M:%S')
                    placeholder.info(f"監視中... 次のスキャンは3分後 ({now_str})")
                    for t in current_watchlist:
                        df = get_stock_data(t)
                        if df is not None:
                            sigs = judge_jack_laws(df, t)
                            if sigs:
                                requests.post(DISCORD_URL, json={"content": f"🔔 **{t}**\n{', '.join(sigs)}"})
                                st.toast(f"{t} シグナル検知")
                    time.sleep(180)
                else:
                    placeholder.warning("現在、監視時間外です (09:20〜15:20)")
                    time.sleep(60)
