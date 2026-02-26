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

st.set_page_config(page_title="Jack株AI：究極監視版", layout="centered")

# --- 日本時間(JST)取得 ---
def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

def get_business_days_diff(start_date_str):
    try:
        start_date = pd.to_datetime(start_date_str).date()
        return len(pd.bdate_range(start=start_date, end=get_jst_now().date()))
    except: return 1

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
                return [i for i in data if get_business_days_diff(i['added_date']) <= 4]
        except: return []
    return []

# --- RCI計算 ---
def calculate_rci(series, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- 指標計算＆判定 (1分足) ---
def get_analysis(ticker):
    try:
        raw = yf.download(ticker, period="5d", interval="1m", progress=False)
        if raw.empty: return None
        df = raw.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.apply(pd.to_numeric, errors='coerce')
        df['MA60'] = ta.sma(df['Close'], length=60); df['MA200'] = ta.sma(df['Close'], length=200)
        df['MA60_slope'] = df['MA60'].diff(); df['MA200_slope'] = df['MA200'].diff()
        bb = ta.bbands(df['Close'], length=20, std=2); bb3 = ta.bbands(df['Close'], length=20, std=3)
        if bb is None or bb3 is None: return None
        df['BB_up_2'] = bb['BBU_20_2.0']; df['BB_low_3'] = bb3['BBL_20_3.0']
        macd = ta.macd(df['Close']); df['MACD'] = macd['MACD_12_26_9']; df['MACD_S'] = macd['MACDs_12_26_9']
        df['RSI'] = ta.rsi(df['Close'], length=14)
        ha = ta.ha(df['Open'], df['High'], df['Low'], df['Close'])
        df['HA_O'] = ha['HA_open']; df['HA_C'] = ha['HA_close']
        return df
    except: return None

def check_laws(df, ticker):
    last = df.iloc[-1]; prev = df.iloc[-2]; sigs = []
    rsi_txt = f"(RSI:{last['RSI']:.1f})"
    is_down = (last['MA60_slope'] < 0) and (last['MA200_slope'] < 0)
    
    if last['RSI'] <= 10 or last['RSI'] >= 80: sigs.append(f"🚨【RSI極限】{rsi_txt}")
    if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
        sigs.append(f"法則1:強気限界(売) {rsi_txt}")
    if last['Close'] < last['MA60'] and last['Low'] <= last['BB_low_3']:
        prefix = "⚠️【注意】" if is_down and last['HA_C'] <= last['HA_O'] else "🔥"
        sigs.append(f"{prefix}法則4:BB-3σ接触(買) {rsi_txt}")
    if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
        prefix = "💎【超王道】" if is_down else "💎"
        sigs.append(f"{prefix}法則6:60MA反発(売) {rsi_txt}")
    return sigs

# --- UI メイン ---
tab1, tab2 = st.tabs(["🌙 銘柄選別 (RCI・最低RSI)", "☀️ 精密監視 (1分足)"])

with tab1:
    st.subheader("🌙 夜の選別：スイング予測")
    rsi_val = st.slider("抽出するRSIライン", 10, 60, 40)
    if st.button("全銘柄スキャン開始"):
        found = []; bar = st.progress(0); tickers = list(JPX400_DICT.keys())
        all_data = yf.download(tickers, period="200d", interval="1d", group_by='ticker', progress=False)
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers))
            try:
                df_d = all_data[t].dropna()
                rsi_s = ta.rsi(df_d['Close'], length=14)
                min_rsi = rsi_s.tail(4).min()
                if min_rsi <= rsi_val:
                    rci9 = calculate_rci(df_d['Close'], 9).iloc[-1]
                    found.append({"ticker": t, "mr": min_rsi, "r9": rci9})
            except: continue
        st.session_state.found = found

    if 'found' in st.session_state:
        st.write("### 検索結果（まとめて保存できます）")
        selected = []
        for item in st.session_state.found:
            t = item['ticker']
            label = f"{t} {JPX400_DICT.get(t)} | 最低RSI:{item['mr']:.1f} | RCI9:{item['r9']:.1f}"
            if st.checkbox(label, value=True, key=f"sel_{t}"):
                selected.append(t)
        
        if st.button("✅ 選択した銘柄をまとめて保存"):
            today_str = get_jst_now().strftime('%Y-%m-%d')
            existing = load_watchlist()
            for s_t in selected:
                if s_t not in [x['ticker'] for x in existing]:
                    existing.append({"ticker": s_t, "added_date": today_str})
            with open(WATCHLIST_FILE, 'w') as f: json.dump(existing, f)
            st.success(f"{len(selected)}銘柄を保存しました。精密監視タブへ！")

with tab2:
    watch_data = load_watchlist()
    jst_now = get_jst_now()
    st.write(f"🕰 **現在の日本時間: {jst_now.strftime('%H:%M:%S')}**")
    
    # 強制停止ボタンの復活
    if st.button("🔴 監視を完全に停止する", type="primary"):
        st.session_state.manual_stop = True
        send_discord("🛑 【システム】友幸さんにより監視が強制停止されました。")
        st.rerun()

    # 監視リスト表示を実装
    if watch_data:
        with st.expander("📋 現在の監視リストを表示", expanded=True):
            for i in watch_data:
                diff = get_business_days_diff(i['added_date'])
                st.write(f"・**{i['ticker']} ({JPX400_DICT.get(i['ticker'])})** - {diff}営業日目")
        
        if st.button("🗑️ リストを空にする"):
            if os.path.exists(WATCHLIST_FILE): os.remove(WATCHLIST_FILE)
            st.rerun()

    if not st.session_state.get('manual_stop'):
        now_time = jst_now.time()
        is_trading = (dt_time(9, 20) <= now_time <= dt_time(11, 50)) or (dt_time(12, 50) <= now_time <= dt_time(15, 20))
        
        if is_trading and watch_data:
            if 'last_status' not in st.session_state:
                send_discord(f"▶️ 【システム】監視を開始します。対象: {len(watch_data)}銘柄")
                st.session_state.last_status = 'running'
            
            placeholder = st.empty()
            for item in watch_data:
                df = get_analysis(item['ticker'])
                if df is not None:
                    sigs = check_laws(df, item['ticker'])
                    for s in sigs: send_discord(f"🔔 **{item['ticker']} {JPX400_DICT.get(item['ticker'])}**\n{s}")
            
            for i in range(180, 0, -1):
                placeholder.success(f"🚀 精密監視中... ({get_jst_now().strftime('%H:%M:%S')}) \n\n ⏳ 次まで: {i}秒")
                time.sleep(1)
            st.rerun()
        else:
            if st.session_state.get('last_status') == 'running':
                send_discord("🕒 【システム】時間外またはお昼休みのため待機します。")
                st.session_state.last_status = 'standby'
            st.info("🕒 現在は待機中です（9:20-11:50, 12:50-15:20に自動稼働）。")
            time.sleep(60); st.rerun()
    else:
        st.warning("現在、監視を強制停止しています。")
        if st.button("▶️ 監視を再開する"):
            del st.session_state.manual_stop; st.rerun()
