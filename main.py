import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import json
import os
from datetime import datetime, time as dt_time, timedelta, timezone
import time

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：トレンド検知強化版", layout="centered")

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

def get_clean_df(ticker):
    try:
        raw = yf.download(ticker, period="5d", interval="1m", progress=False)
        if raw.empty: return None
        df = raw.copy()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df.apply(pd.to_numeric, errors='coerce')
    except: return None

# --- 新・判定ロジック：MAの向きを検知 ---
def check_laws(df, ticker):
    try:
        # 指標計算
        df['MA60'] = ta.sma(df['Close'], length=60)
        df['MA200'] = ta.sma(df['Close'], length=200)
        
        # 【新機能】MAの傾き（前1分との差）を計算
        df['MA60_slope'] = df['MA60'].diff()
        df['MA200_slope'] = df['MA200'].diff()
        
        bb = ta.bbands(df['Close'], length=20, std=2)
        bb3 = ta.bbands(df['Close'], length=20, std=3)
        if bb is None or bb3 is None: return []
        df['BB_up_2'] = bb['BBU_20_2.0']; df['BB_low_3'] = bb3['BBL_20_3.0']
        
        macd = ta.macd(df['Close']); df['MACD'] = macd['MACD_12_26_9']; df['MACD_S'] = macd['MACDs_12_26_9']
        df['RSI'] = ta.rsi(df['Close'], length=14)
        
        ha = ta.ha(df['Open'], df['High'], df['Low'], df['Close'])
        df['HA_O'] = ha['HA_open']; df['HA_C'] = ha['HA_close']

        last = df.iloc[-1]; prev = df.iloc[-2]; sigs = []
        rsi_txt = f"(RSI:{last['RSI']:.1f})"
        
        # トレンド・向きの判定
        is_same_down = (last['MA60_slope'] < 0) and (last['MA200_slope'] < 0)
        is_same_up = (last['MA60_slope'] > 0) and (last['MA200_slope'] > 0)
        is_down_trend = last['MA200'] > last['MA60']

        # 1. 60MA上 & BB+2σ 3回接触
        if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
            sigs.append(f"法則1:強気限界(売) {rsi_txt}")

        # 4. 60MA下 & BB-3σ接触 (東宝のパターン)
        if last['Close'] < last['MA60'] and last['Low'] <= last['BB_low_3']:
            if is_same_down:
                # 強い下落中は陽転するまで「逆張り注意」
                prefix = "⚠️【超・逆張り注意】" if last['HA_C'] <= last['HA_O'] else "🔥【短期リバ】"
                sigs.append(f"{prefix}法則4:BB-3σ接触(買) - 強下降中 {rsi_txt}")
            else:
                sigs.append(f"法則4:BB-3σ反発(買) {rsi_txt}")

        # 6. 60MA下 & 60MA反発 (東宝で連発した戻り売り)
        if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
            label = "💎【超・王道】" if is_same_down else "💎【王道】"
            sigs.append(f"{label}法則6:60MA反発(売) - 下降トレンド継続中 {rsi_txt}")

        # 6. 60MA突破 (トレンド転換)
        if last['Close'] > last['MA60'] and prev['Close'] < last['MA60'] and last['HA_C'] > last['HA_O'] and last['MACD'] > last['MACD_S']:
            label = "🚀【超・最強転換】" if is_same_up else "★最強転換"
            sigs.append(f"法則6:60MA突破(買) {label} {rsi_txt}")

        return sigs
    except: return []

# --- UI メイン ---
tab1, tab2 = st.tabs(["🌙 夜の選別", "☀️ 精密監視"])

with tab1:
    st.subheader("銘柄検索")
    rsi_val = st.slider("抽出ライン", 10, 60, 40)
    if st.button("全銘柄スキャン開始"):
        found = []; bar = st.progress(0); tickers = list(JPX400_DICT.keys())
        all_data = yf.download(tickers, period="40d", interval="1d", group_by='ticker', progress=False)
        for i, t in enumerate(tickers):
            bar.progress((i + 1) / len(tickers))
            try:
                df_d = all_data[t].dropna()
                rsi_s = ta.rsi(df_d['Close'], length=14)
                min_rsi = rsi_s.tail(4).min()
                if min_rsi <= rsi_val: found.append({"ticker": t, "mr": min_rsi})
            except: continue
        st.session_state.found = found
    if 'found' in st.session_state:
        selected = []
        for item in st.session_state.found:
            if st.checkbox(f"{item['ticker']} {JPX400_DICT.get(item['ticker'])}", value=True, key=item['ticker']):
                selected.append(item['ticker'])
        if st.button("選定銘柄を保存"):
            data = [{"ticker": s_t, "added_date": get_jst_now().strftime('%Y-%m-%d')} for s_t in selected]
            with open(WATCHLIST_FILE, 'w') as f: json.dump(data, f)
            st.success("保存完了！")

with tab2:
    watch_data = load_watchlist()
    jst_now = get_jst_now()
    now_time = jst_now.time()
    
    if st.button("🔴 監視を完全に停止する", type="primary"):
        st.session_state.manual_stop = True
        send_discord("🛑 【システム】強制停止されました。")
        st.rerun()

    if not st.session_state.get('manual_stop'):
        # 監視時間・お昼休み判定 (9:20-11:50, 12:50-15:20)
        is_trading = (dt_time(9, 20) <= now_time <= dt_time(11, 50)) or (dt_time(12, 50) <= now_time <= dt_time(15, 20))
        
        if is_trading:
            status_p = st.empty()
            for item in watch_data:
                df = get_clean_df(item['ticker'])
                if df is not None and len(df) >= 200:
                    sigs = check_laws(df, item['ticker'])
                    for s in sigs: send_discord(f"🔔 **{item['ticker']} {JPX400_DICT.get(item['ticker'])}**\n{s}")
            
            for i in range(180, 0, -1):
                status_p.success(f"🚀 精密監視中... ({get_jst_now().strftime('%H:%M:%S')}) \n\n ⏳ 次まで: {i}秒")
                time.sleep(1)
            st.rerun()
        else:
            st.info(f"🕒 取引時間外またはお昼休みです。 (日本時間: {jst_now.strftime('%H:%M:%S')})")
            time.sleep(600); st.rerun()
    else:
        st.warning("現在、監視を停止しています。")
        if st.button("▶️ 監視を再開する"):
            del st.session_state.manual_stop; st.rerun()
