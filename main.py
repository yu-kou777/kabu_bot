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

JPX400_DICT = {
    '1605.T': 'INPEX', '1801.T': '大成建設', '1802.T': '大林組', '1925.T': '大和ハウス',
    '2502.T': 'アサヒ', '2802.T': '味の素', '2914.T': 'JT', '4063.T': '信越化学',
    '4502.T': '武田薬品', '4503.T': 'アステラス', '4519.T': '中外製薬', '4568.T': '第一三共',
    '4661.T': 'オリエンタルランド', '4901.T': '富士フイルム', '5401.T': '日本製鉄', '5713.T': '住友鉱山',
    '6301.T': '小松製作所', '6367.T': 'ダイキン', '6501.T': '日立', '6758.T': 'ソニーG',
    '6857.T': 'アドバンテスト', '6920.T': 'レーザーテック', '6954.T': 'ファナック', '6981.T': '村田製作所',
    '7203.T': 'トヨタ', '7267.T': 'ホンダ', '7741.T': 'HOYA', '7974.T': '任天堂',
    '8001.T': '伊藤忠', '8031.T': '三井物産', '8035.T': '東京エレクトロン', '8058.T': '三菱商事',
    '8306.T': '三菱UFJ', '8316.T': '三井住友', '8411.T': 'みずほFG', '8766.T': '東京海上',
    '8801.T': '三井不動産', '9020.T': 'JR東日本', '9101.T': '日本郵船', '9104.T': '商船三井',
    '9432.T': 'NTT', '9433.T': 'KDDI', '9983.T': 'ファーストリテイリング', '9984.T': 'ソフトバンクG'
}

st.set_page_config(page_title="Jack株AI監視", layout="centered")

def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message})
    except: pass

def get_business_days_diff(start_date_str):
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    today = datetime.now().date()
    return len(pd.bdate_range(start=start_date, end=today))

def save_watchlist(new_tickers):
    existing_list = load_raw_watchlist()
    today_str = datetime.now().strftime('%Y-%m-%d')
    for t in new_tickers:
        if t not in [item['ticker'] for item in existing_list]:
            existing_list.append({"ticker": t, "added_date": today_str})
    with open(WATCHLIST_FILE, 'w') as f: json.dump(existing_list, f)
    st.session_state['current_watchlist'] = existing_list

def load_raw_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f: return json.load(f)
        except: return []
    return []

def load_and_filter_watchlist():
    raw_list = load_raw_watchlist()
    filtered_list = []
    for item in raw_list:
        if get_business_days_diff(item['added_date']) <= 4:
            filtered_list.append(item)
    if len(raw_list) != len(filtered_list):
        with open(WATCHLIST_FILE, 'w') as f: json.dump(filtered_list, f)
    return filtered_list

def get_stock_data(ticker):
    try:
        df = yf.download(ticker, period="5d", interval="1m", progress=False)
        if df.empty or len(df) < 60: return None
        df['MA60'] = ta.sma(df['Close'], length=60); df['MA200'] = ta.sma(df['Close'], length=200)
        bb = ta.bbands(df['Close'], length=20, std=2); df['BB_up_2'] = bb['BBU_20_2.0']
        bb3 = ta.bbands(df['Close'], length=20, std=3); df['BB_low_3'] = bb3['BBL_20_3.0']
        macd = ta.macd(df['Close']); df['MACD'] = macd['MACD_12_26_9']; df['MACD_S'] = macd['MACDs_12_26_9']
        df['VOL_MA'] = ta.sma(df['Volume'], length=20); df['RSI'] = ta.rsi(df['Close'], length=14)
        ha = ta.ha(df['Open'], df['High'], df['Low'], df['Close'])
        df['HA_O'] = ha['HA_open']; df['HA_C'] = ha['HA_close']
        return df
    except: return None

def judge_jack_laws(df, ticker):
    last = df.iloc[-1]; prev = df.iloc[-2]; sigs = []
    is_ha_green = last['HA_C'] > last['HA_O']
    is_macd_bullish = last['MACD'] > last['MACD_S']
    is_vol_spike = last['Volume'] > last['VOL_MA'] * 1.5
    curr_rsi = last['RSI']
    rsi_info = f"(RSI:{curr_rsi:.1f})"
    
    # 【新規】限界突破アラート (10以下 / 80以上)
    if curr_rsi <= 10.0:
        sigs.append(f"🚨【RSI限界突破】10以下! 極限の売られすぎ {rsi_info}")
    elif curr_rsi >= 80.0:
        sigs.append(f"🚨【RSI限界突破】80以上! 極限の買われすぎ {rsi_info}")

    # 友幸さんの6つの法則
    if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
        sigs.append(f"法則1:強気限界(売) {rsi_info}")
    if last['Close'] > last['MA60']:
        if last['Low'] <= last['MA60'] and is_ha_green: sigs.append(f"法則2:60MA反発(買) {rsi_info}")
        if last['Close'] < last['MA60']: sigs.append(f"法則2:60MA割れ(売) {rsi_info}")
    if last['MA200'] > last['MA60'] and last['High'] >= last['MA200']:
        sigs.append(f"法則3:200MA抵抗(売) {rsi_info}")
    if last['Close'] < last['MA60'] and last['Low'] <= last['BB_low_3']:
        sigs.append(f"法則4:BB-3σ反発(買) {'🔥大商い' if is_vol_spike else ''} {rsi_info}")
    if last['Close'] < last['MA60']:
        if last['Low'] <= last['MA200'] and is_macd_bullish: sigs.append(f"法則5:200MA反発(買) {rsi_info}")
        if last['Close'] < last['MA200']: sigs.append(f"法則5:200MA割れ(売) {rsi_info}")
    if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
        sigs.append(f"法則6:60MA反発(売) {rsi_info}")
    if last['Close'] > last['MA60'] and prev['Close'] < prev['MA60'] and is_ha_green and is_macd_bullish:
        sigs.append(f"法則6:60MA突破(買) ★最強 {rsi_info}")
    return sigs

# --- UI (スキャン/監視) ---
st.title("📈 Jack株AI：最強版監視")

if 'current_watchlist' not in st.session_state:
    st.session_state['current_watchlist'] = load_and_filter_watchlist()

tab1, tab2 = st.tabs(["🌙 4日間最低RSI選別", "☀️ 精密監視"])

with tab1:
    st.subheader("直近4日間の最低RSIでスキャン")
    rsi_val = st.slider("抽出する最低RSIライン", 10, 60, 40)
    col1, col2 = st.columns(2)
    if col1.button("スキャン開始"):
        found = []; bar = st.progress(0)
        all_data = yf.download(list(JPX400_DICT.keys()), period="40d", interval="1d", group_by='ticker', progress=False)
        for i, t in enumerate(JPX400_DICT.keys()):
            bar.progress((i + 1) / len(JPX400_DICT))
            df_d = all_data[t].dropna()
            if len(df_d) < 18: continue
            rsi_s = ta.rsi(df_d['Close'], length=14)
            if rsi_s is not None and not rsi_s.empty:
                min_rsi_4d = rsi_s.tail(4).min()
                if min_rsi_4d <= rsi_val:
                    found.append({"ticker": t, "min_rsi": min_rsi_4d, "cr": rsi_s.iloc[-1], "p": df_d['Close'].iloc[-1]})
        st.session_state.found = found
    if col2.button("リセット"): 
        if os.path.exists(WATCHLIST_FILE): os.remove(WATCHLIST_FILE)
        st.session_state['current_watchlist'] = []; st.rerun()

    if 'found' in st.session_state:
        selected = []
        for item in st.session_state.found:
            t, mr, cr, p = item['ticker'], item['min_rsi'], item['cr'], item['p']
            st.info(f"**{t} {JPX400_DICT.get(t)}** | 4日内最低: {mr:.1f} | 現在: {cr:.1f}")
            if st.checkbox(f"登録", value=True, key=f"sel_{t}"): selected.append(t)
        if st.button("選定銘柄を保存"): save_watchlist(selected); st.success("保存完了。")

with tab2:
    watch_data = st.session_state['current_watchlist']
    if not watch_data: st.warning("監視銘柄がありません。")
    else:
        st.write("📋 **監視中銘柄（4営業日保持）**")
        for item in watch_data:
            st.write(f"・{item['ticker']} ({get_business_days_diff(item['added_date'])}営業日目)")
        c1, c2 = st.columns(2)
        if c1.button("▶️ 監視スタート"): st.session_state.monitoring = True; send_discord("▶️ 限界突破監視を開始。"); st.rerun()
        if c2.button("⚠️ 強制停止", type="primary"): st.session_state.monitoring = False; send_discord("⏹️ 停止。"); st.rerun()

        if st.session_state.monitoring:
            p = st.empty()
            while st.session_state.monitoring:
                now = datetime.now()
                if dt_time(9, 20) <= now.time() <= dt_time(15, 20):
                    p.info(f"🚀 限界RSI/6つの法則 監視中... ({now.strftime('%H:%M:%S')})")
                    for item in watch_data:
                        t = item['ticker']; df = get_stock_data(t)
                        if df is not None:
                            sigs = judge_jack_laws(df, t)
                            for s in sigs: send_discord(f"🔔 **{t} {JPX400_DICT.get(t)}**\n{s}")
                    for i in range(180, 0, -1):
                        if not st.session_state.monitoring: break
                        p.info(f"⏳ 次の解析まで残り {i} 秒...")
                        time.sleep(1)
                else:
                    st.session_state.monitoring = False; send_discord("🕒 自動終了。"); st.rerun(); break
