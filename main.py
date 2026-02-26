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

st.set_page_config(page_title="Jack株AI：RCI予測スキャン", layout="centered")

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

# --- RCI計算関数 ---
def calculate_rci(series, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- 判定ロジック（1分足監視用） ---
def check_laws(df, ticker):
    try:
        df['MA60'] = ta.sma(df['Close'], length=60); df['MA200'] = ta.sma(df['Close'], length=200)
        df['MA60_slope'] = df['MA60'].diff(); df['MA200_slope'] = df['MA200'].diff()
        bb = ta.bbands(df['Close'], length=20, std=2); bb3 = ta.bbands(df['Close'], length=20, std=3)
        df['BB_up_2'] = bb['BBU_20_2.0']; df['BB_low_3'] = bb3['BBL_20_3.0']
        macd = ta.macd(df['Close']); df['MACD'] = macd['MACD_12_26_9']; df['MACD_S'] = macd['MACDs_12_26_9']
        df['RSI'] = ta.rsi(df['Close'], length=14)
        ha = ta.ha(df['Open'], df['High'], df['Low'], df['Close'])
        df['HA_O'] = ha['HA_open']; df['HA_C'] = ha['HA_close']
        last = df.iloc[-1]; sigs = []
        rsi_txt = f"(RSI:{last['RSI']:.1f})"
        is_same_down = (last['MA60_slope'] < 0) and (last['MA200_slope'] < 0)
        if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
            sigs.append(f"法則1:強気限界(売) {rsi_txt}")
        if last['Close'] < last['MA60'] and last['Low'] <= last['BB_low_3']:
            prefix = "⚠️【超・逆張り注意】" if is_same_down and last['HA_C'] <= last['HA_O'] else "🔥"
            sigs.append(f"{prefix}法則4:BB-3σ接触(買) {rsi_txt}")
        if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
            label = "💎【超・王道】" if is_same_down else "💎【王道】"
            sigs.append(f"{label}法則6:60MA反発(売) {rsi_txt}")
        return sigs
    except: return []

# --- UI メイン ---
tab1, tab2 = st.tabs(["🌙 日足RCI予測（夜の選別）", "☀️ 3分精密監視"])

with tab1:
    st.subheader("日足RCI 3本線シンクロスキャン")
    st.write("短期(9), 中期(26), 長期(52)のRCIから反転兆候を予測します。")
    if st.button("RCIスイング予測を開始"):
        found = []; bar = st.progress(0); tickers = list(JPX400_DICT.keys())
        all_data = yf.download(tickers, period="200d", interval="1d", group_by='ticker', progress=False)
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers))
            try:
                df_d = all_data[t].dropna()
                if len(df_d) < 60: continue
                rci9 = calculate_rci(df_d['Close'], 9); rci26 = calculate_rci(df_d['Close'], 26); rci52 = calculate_rci(df_d['Close'], 52)
                r9, r26, r52 = rci9.iloc[-1], rci26.iloc[-1], rci52.iloc[-1]
                p9, p26, p52 = rci9.iloc[-2], rci26.iloc[-2], rci52.iloc[-2]
                # 予測ロジック：短期が底から反転し、中期・長期が上昇トレンド
                if r9 > p9 and p9 < -80 and r52 > -50:
                    found.append({"ticker": t, "type": "💎絶好の押し目", "r9": r9, "r52": r52})
                elif r9 > p9 and p26 < -80 and p52 < -80:
                    found.append({"ticker": t, "type": "🚀大底からの反転", "r9": r9, "r52": r52})
            except: continue
        st.session_state.rci_found = found

    if 'rci_found' in st.session_state:
        for item in st.session_state.rci_found:
            t = item['ticker']
            st.info(f"**{t} {JPX400_DICT.get(t)}** - {item['type']} (RCI9:{item['r9']:.1f})")
            if st.checkbox(f"精密監視リストに登録", value=True, key=f"rci_{t}"):
                # 既存の保存ロジックと連携
                if st.button(f"確定: {t}", key=f"btn_{t}"):
                    existing = []
                    if os.path.exists(WATCHLIST_FILE):
                        with open(WATCHLIST_FILE, 'r') as f: existing = json.load(f)
                    existing.append({"ticker": t, "added_date": get_jst_now().strftime('%Y-%m-%d')})
                    with open(WATCHLIST_FILE, 'w') as f: json.dump(existing, f); st.success("保存完了")

with tab2:
    # 既存の3分精密監視ロジック（そのまま維持）
    jst_now = get_jst_now(); now_time = jst_now.time()
    st.write(f"現在時刻: {jst_now.strftime('%H:%M:%S')}")
    # ... (前回の監視コードが続く)
