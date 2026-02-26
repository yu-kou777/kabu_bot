import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import json
import os
from datetime import datetime, time as dt_time, timedelta
import time

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：選別と3分監視", layout="centered")

# --- 共通関数 ---
def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

def get_business_days_diff(start_date_str):
    try:
        start_date = pd.to_datetime(start_date_str).date()
        return len(pd.bdate_range(start=start_date, end=datetime.now().date()))
    except: return 1

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f:
                data = json.load(f)
                return [item for item in data if get_business_days_diff(item['added_date']) <= 4]
        except: return []
    return []

def save_watchlist(tickers):
    existing = load_watchlist()
    today_str = datetime.now().strftime('%Y-%m-%d')
    for t in tickers:
        if t not in [x['ticker'] for x in existing]:
            existing.append({"ticker": t, "added_date": today_str})
    with open(WATCHLIST_FILE, 'w') as f: json.dump(existing, f)
    st.session_state['current_watchlist'] = existing

# --- 指標計算 (エラーガード強化) ---
def get_clean_df(ticker, period="5d", interval="1m"):
    try:
        raw = yf.download(ticker, period=period, interval=interval, progress=False)
        if raw.empty: return None
        df = raw.copy()
        # MultiIndex対策
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except: return None

def check_laws(df, ticker):
    try:
        # 指標計算
        df['MA60'] = ta.sma(df['Close'], length=60)
        df['MA200'] = ta.sma(df['Close'], length=200)
        bb = ta.bbands(df['Close'], length=20, std=2)
        bb3 = ta.bbands(df['Close'], length=20, std=3)
        if bb is None or bb3 is None: return []
        
        df['BB_up_2'] = bb['BBU_20_2.0']
        df['BB_low_3'] = bb3['BBL_20_3.0']
        macd = ta.macd(df['Close'])
        df['MACD'] = macd['MACD_12_26_9']; df['MACD_S'] = macd['MACDs_12_26_9']
        df['RSI'] = ta.rsi(df['Close'], length=14)
        ha = ta.ha(df['Open'], df['High'], df['Low'], df['Close'])
        df['HA_O'] = ha['HA_open']; df['HA_C'] = ha['HA_close']

        last = df.iloc[-1]; prev = df.iloc[-2]; sigs = []
        is_down = last['MA200'] > last['MA60']
        rsi_txt = f"(RSI:{last['RSI']:.1f})"

        # 法則判定
        if last['RSI'] <= 10 or last['RSI'] >= 80: sigs.append(f"🚨【RSI極限値】{rsi_txt}")
        if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
            sigs.append(f"法則1:強気限界(売) {rsi_txt}")
        if last['Close'] < last['MA60'] and last['Low'] <= last['BB_low_3']:
            prefix = "⚠️【逆張り注意】" if is_down and last['HA_C'] <= last['HA_O'] else "🔥"
            sigs.append(f"{prefix}法則4:BB-3σ接触(買) {rsi_txt}")
        if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
            prefix = "💎【王道】" if is_down else ""
            sigs.append(f"{prefix}法則6:60MA反発(売) {rsi_txt}")
        return sigs
    except: return []

# --- UI (タブ構造の復活) ---
tab1, tab2 = st.tabs(["🌙 夜の選別", "☀️ 精密監視"])

with tab1:
    st.subheader("直近4日内最低RSI選別")
    rsi_val = st.slider("抽出ライン", 10, 60, 40)
    if st.button("全銘柄スキャン開始"):
        found = []; bar = st.progress(0)
        tickers = list(JPX400_DICT.keys())
        all_data = yf.download(tickers, period="40d", interval="1d", group_by='ticker', progress=False)
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers))
            try:
                df_d = all_data[t].dropna()
                if len(df_d) < 18: continue
                rsi_s = ta.rsi(df_d['Close'], length=14)
                min_rsi = rsi_s.tail(4).min()
                if min_rsi <= rsi_val:
                    found.append({"ticker": t, "mr": min_rsi, "cr": rsi_s.iloc[-1]})
            except: continue
        st.session_state.found = found

    if 'found' in st.session_state:
        selected = []
        for item in st.session_state.found:
            t, mr, cr = item['ticker'], item['mr'], item['cr']
            st.write(f"**{t} {JPX400_DICT.get(t)}** | 4日内最低RSI: {mr:.1f}")
            if st.checkbox(f"登録", value=True, key=f"sel_{t}"): selected.append(t)
        if st.button("選定銘柄を保存"):
            save_watchlist(selected); st.success("監視リストに保存しました。")

with tab2:
    watch_data = load_watchlist()
    if not watch_data:
        st.warning("監視銘柄がありません。夜の選別タブで追加してください。")
    else:
        st.info(f"📋 監視対象: {len(watch_data)}銘柄")
        if st.button("⚠️ リセット", type="primary"):
            if os.path.exists(WATCHLIST_FILE): os.remove(WATCHLIST_FILE)
            st.rerun()

        now = datetime.now().time()
        if dt_time(9, 20) <= now <= dt_time(15, 20):
            placeholder = st.empty()
            while True:
                placeholder.info(f"🚀 精密監視中... ({datetime.now().strftime('%H:%M:%S')})")
                for item in watch_data:
                    df = get_clean_df(item['ticker'])
                    if df is not None and len(df) >= 200:
                        sigs = check_laws(df, item['ticker'])
                        for s in sigs: send_discord(f"🔔 **{item['ticker']} {JPX400_DICT.get(item['ticker'])}**\n{s}")
                time.sleep(180); st.rerun()
        else:
            st.warning("🕒 時間外です。9:20に自動再開します。")
            # 時間外でもDiscord連携を確認したい場合、ここを通ると通知が飛びます
            if 'last_off_msg' not in st.session_state:
                send_discord("🕒 監視時間外のため待機中です。銘柄選別は「夜の選別」タブで行えます。")
                st.session_state.last_off_msg = True
