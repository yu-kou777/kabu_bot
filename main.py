import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import json
import os
from datetime import datetime, time as dt_time
import time

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"

# JPX400 主要銘柄
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
    try:
        requests.post(DISCORD_URL, json={"content": message})
    except:
        pass

def save_watchlist(tickers):
    with open(WATCHLIST_FILE, 'w') as f: json.dump(tickers, f)
    st.session_state['current_watchlist'] = tickers

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f: return json.load(f)
    return []

def get_stock_data(ticker):
    try:
        df = yf.download(ticker, period="5d", interval="1m", progress=False)
        if df.empty or len(df) < 60: return None
        df['MA60'] = ta.sma(df['Close'], length=60); df['MA200'] = ta.sma(df['Close'], length=200)
        bb = ta.bbands(df['Close'], length=20, std=2); df['BB_up_2'] = bb['BBU_20_2.0']
        bb3 = ta.bbands(df['Close'], length=20, std=3); df['BB_low_3'] = bb3['BBL_20_3.0']
        return df
    except: return None

def judge_jack_laws(df, ticker):
    last = df.iloc[-1]; prev = df.iloc[-2]; sigs = []
    # 友幸さんの6つの法則
    if last['Close'] > last['MA60'] and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
        sigs.append("法則1:強気限界(売)")
    if last['Close'] > last['MA60']:
        if last['Low'] <= last['MA60']: sigs.append("法則2:60MA反発(買)")
        if last['Close'] < last['MA60']: sigs.append("法則2:60MA割れ(売)")
    if last['MA200'] > last['MA60'] and last['High'] >= last['MA200']:
        sigs.append("法則3:200MA抵抗(売)")
    if last['Close'] < last['MA60'] and last['Low'] <= last['BB_low_3']:
        sigs.append("法則4:BB-3σ反発(買)")
    if last['Close'] < last['MA60']:
        if last['Low'] <= last['MA200']: sigs.append("法則5:200MA反発(買)")
        if last['Close'] < last['MA200']: sigs.append("法則5:200MA割れ(売)")
    if last['Close'] < last['MA60'] and last['High'] >= last['MA60']:
        sigs.append("法則6:60MA反発(売)")
    if last['Close'] > last['MA60'] and prev['Close'] < prev['MA60']:
        sigs.append("法則6:60MA突破(買)")
    return sigs

# 状態初期化
if 'current_watchlist' not in st.session_state: st.session_state['current_watchlist'] = load_watchlist()
if 'monitoring' not in st.session_state: st.session_state['monitoring'] = False

tab1, tab2 = st.tabs(["🌙 夜の選別", "☀️ 3分刻み監視"])

with tab1:
    st.subheader("日足RSIスクリーニング")
    rsi_val = st.slider("抽出ライン(RSI)", 10, 60, 40)
    col1, col2 = st.columns(2)
    if col1.button("全銘柄スキャン開始"):
        found = []; bar = st.progress(0)
        all_data = yf.download(list(JPX400_DICT.keys()), period="40d", interval="1d", group_by='ticker', progress=False)
        for i, t in enumerate(JPX400_DICT.keys()):
            bar.progress((i + 1) / len(JPX400_DICT))
            df_d = all_data[t].dropna()
            if len(df_d) < 15: continue
            rsi_s = ta.rsi(df_d['Close'], length=14)
            if rsi_s is not None and not rsi_s.empty:
                curr_rsi = rsi_s.iloc[-1]
                if curr_rsi <= rsi_val: found.append({"ticker": t, "rsi": curr_rsi, "price": df_daily['Close'].iloc[-1] if 'df_daily' in locals() else 0})
        st.session_state.found = found
    if col2.button("リセット"): save_watchlist([]); st.rerun()

    if 'found' in st.session_state:
        selected = []
        for item in st.session_state.found:
            t, r = item['ticker'], item['rsi']
            st.info(f"**{t} {JPX400_DICT.get(t)}** | RSI: {r:.1f}")
            if st.checkbox(f"登録", value=True, key=f"sel_{t}"): selected.append(t)
        if st.button("選定銘柄を保存"): save_watchlist(selected); st.success("保存完了")

with tab2:
    watch_list = st.session_state['current_watchlist']
    if not watch_list: st.warning("銘柄がありません。")
    else:
        st.info(f"📋 監視対象: {', '.join([f'{t}({JPX400_DICT.get(t)})' for t in watch_list])}")
        c1, c2 = st.columns(2)
        
        # スタートボタン
        if c1.button("▶️ 監視スタート", disabled=st.session_state.monitoring):
            st.session_state.monitoring = True
            send_discord("▶️ 友幸さんの株AI監視を開始しました。")
            st.rerun()
            
        # 強制停止ボタン
        if c2.button("⚠️ 強制停止", type="primary", disabled=not st.session_state.monitoring):
            st.session_state.monitoring = False
            send_discord("⏹️ 友幸さんにより、監視が強制停止されました。")
            st.rerun()

        if st.session_state.monitoring:
            placeholder = st.empty()
            while st.session_state.monitoring:
                now = datetime.now()
                # 監視時間判定
                if dt_time(9, 20) <= now.time() <= dt_time(15, 20):
                    placeholder.info(f"🚀 監視中... ({now.strftime('%H:%M:%S')})")
                    for t in watch_list:
                        df = get_stock_data(t)
                        if df is not None:
                            sigs = judge_jack_laws(df, t)
                            if sigs:
                                send_discord(f"🔔 **{t} {JPX400_DICT.get(t)}**\n{', '.join(sigs)}")
                                st.toast(f"{t} 検知")
                    # 3分間の待機（1秒ごとに停止・時間チェック）
                    for i in range(180, 0, -1):
                        time.sleep(1)
                        # 待機中に停止ボタンが押されたか、時間が過ぎたかをチェック
                        if not st.session_state.monitoring: break
                        check_now = datetime.now().time()
                        if not (dt_time(9, 20) <= check_now <= dt_time(15, 20)):
                            break
                        placeholder.info(f"⏳ 次のスキャンまで残り {i} 秒...")
                else:
                    # 時間外の場合：10秒カウントダウンして強制終了
                    for i in range(10, 0, -1):
                        placeholder.error(f"🕒 監視時間外です。{i}秒後に自動停止し通知します。")
                        time.sleep(1)
                        if not st.session_state.monitoring: break # 途中で停止ボタンが押された場合
                    
                    st.session_state.monitoring = False
                    send_discord("🕒 監視時間外のため、本日の監視を自動終了しました。明日09:20に自動再開予約済。")
                    st.rerun()
                    break
