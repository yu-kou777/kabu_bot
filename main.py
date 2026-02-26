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
    '4901.T': '富士フイルム', '5401.T': '日本製鉄', '5713.T': '住友鉱山', '6301.T': '小松製作所',
    '6367.T': 'ダイキン', '6501.T': '日立', '6758.T': 'ソニーG', '6857.T': 'アドバンテスト',
    '6920.T': 'レーザーテック', '6954.T': 'ファナック', '6981.T': '村田製作所', '7203.T': 'トヨタ',
    '7267.T': 'ホンダ', '7741.T': 'HOYA', '7974.T': '任天堂', '8001.T': '伊藤忠',
    '8031.T': '三井物産', '8035.T': '東京エレクトロン', '8058.T': '三菱商事', '8306.T': '三菱UFJ',
    '8316.T': '三井住友', '8411.T': 'みずほFG', '8766.T': '東京海上', '8801.T': '三井不動産',
    '9020.T': 'JR東日本', '9101.T': '日本郵船', '9104.T': '商船三井', '9432.T': 'NTT',
    '9433.T': 'KDDI', '9983.T': 'ファーストリテイリング', '9984.T': 'ソフトバンクG'
}

st.set_page_config(page_title="Jack株AI監視", layout="centered")

# --- 共通関数 ---
def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

def get_business_days_diff(start_date_str):
    try:
        start_date = pd.to_datetime(start_date_str)
        today = pd.to_datetime(datetime.now().date())
        return len(pd.bdate_range(start=start_date, end=today))
    except: return 1

def load_raw_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f: return json.load(f)
        except: return []
    return []

def save_watchlist_raw(data):
    with open(WATCHLIST_FILE, 'w') as f: json.dump(data, f)

def load_and_filter_watchlist():
    raw_list = load_raw_watchlist()
    filtered_list = []
    for item in raw_list:
        if get_business_days_diff(item['added_date']) <= 4:
            filtered_list.append(item)
    if len(raw_list) != len(filtered_list):
        save_watchlist_raw(filtered_list)
    return filtered_list

# --- 精密ロジック ---
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
    rsi_info = f"(RSI:{last['RSI']:.1f})"
    
    if last['RSI'] <= 10: sigs.append(f"🚨【RSI極限値】10以下! {rsi_info}")
    if last['RSI'] >= 80: sigs.append(f"🚨【RSI極限値】80以上! {rsi_info}")

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

# --- メイン処理 ---
watch_data = load_and_filter_watchlist()

tab1, tab2 = st.tabs(["🌙 4日間最低RSI選別", "☀️ 精密監視"])

with tab1:
    rsi_val = st.slider("抽出ライン(RSI)", 10, 60, 40)
    if st.button("全銘柄スキャン開始"):
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
    
    if st.button("強制リセット"):
        save_watchlist_raw([]); st.rerun()

    if 'found' in st.session_state:
        selected = []
        for item in st.session_state.found:
            t, mr, cr, p = item['ticker'], item['min_rsi'], item['cr'], item['p']
            st.write(f"**{t} {JPX400_DICT.get(t)}** | 4日内最低RSI: {mr:.1f}")
            if st.checkbox(f"登録", value=True, key=f"sel_{t}"): selected.append(t)
        if st.button("選定銘柄を保存"):
            existing = load_raw_watchlist()
            for s_t in selected:
                if s_t not in [x['ticker'] for x in existing]:
                    existing.append({"ticker": s_t, "added_date": datetime.now().strftime('%Y-%m-%d')})
            save_watchlist_raw(existing); st.success("保存完了")

with tab2:
    if not watch_data:
        st.warning("監視銘柄がありません。")
    else:
        st.info(f"📋 監視対象: {len(watch_data)}銘柄")
        if st.button("⚠️ 強制停止", type="primary"):
            st.session_state.stop_signal = True; st.rerun()

        # 【重要】時間内であれば自動で監視ループに入る（強制起動）
        now_time = datetime.now().time()
        if dt_time(9, 20) <= now_time <= dt_time(15, 20):
            if 'stop_signal' not in st.session_state:
                send_discord("▶️ 友幸さんの株AI監視を強制起動しました。")
                placeholder = st.empty()
                while True:
                    placeholder.info(f"🚀 精密監視中... ({datetime.now().strftime('%H:%M:%S')})")
                    for item in watch_data:
                        df = get_stock_data(item['ticker'])
                        if df is not None:
                            sigs = judge_jack_laws(df, item['ticker'])
                            for s in sigs: send_discord(f"🔔 **{item['ticker']} {JPX400_DICT.get(item['ticker'])}**\n{s}")
                    
                    for i in range(180, 0, -1):
                        placeholder.info(f"⏳ 次の解析まで残り {i} 秒...")
                        time.sleep(1)
                        if datetime.now().time() > dt_time(15, 20): break
                    if datetime.now().time() > dt_time(15, 20): break
        else:
            # 【重要】時間外は10秒で停止しDiscord通知
            st.warning("🕒 現在は監視時間外です。10秒後に自動停止します。")
            time.sleep(10)
            send_discord("🕒 時間外のため監視を終了しました。明日09:20に自動再開します。")
            st.stop()
