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
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI監視", layout="centered")

def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r') as f: return json.load(f)
        except: return []
    return []

# --- 判定ロジック ---
def check_laws(df, ticker):
    try:
        last = df.iloc[-1]; prev = df.iloc[-2]; sigs = []
        ma60 = last['MA60']; ma200 = last['MA200']
        is_strong_down = ma200 > ma60
        is_ha_green = last['HA_C'] > last['HA_O']
        is_macd_bullish = last['MACD'] > last['MACD_S']
        rsi_txt = f"(RSI:{last['RSI']:.1f})"

        if last['Close'] > ma60 and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
            sigs.append(f"法則1:強気限界(売) {rsi_txt}")
        if last['Close'] > ma60 and last['Low'] <= ma60 and is_ha_green:
            sigs.append(f"法則2:60MA反発(買) {rsi_txt}")
        if is_strong_down and last['High'] >= ma200:
            sigs.append(f"💎【王道】法則3:200MA抵抗(売) {rsi_txt}")
        if last['Close'] < ma60 and last['Low'] <= last['BB_low_3']:
            prefix = "⚠️【逆張り注意】" if is_strong_down and not is_ha_green else "🔥"
            sigs.append(f"{prefix}法則4:BB-3σ接触(買) {rsi_txt}")
        if last['Close'] < ma60 and last['High'] >= ma60:
            prefix = "💎【王道】" if is_strong_down else ""
            sigs.append(f"{prefix}法則6:60MA反発(売) {rsi_txt}")
        if last['Close'] > ma60 and prev['Close'] < ma60 and is_ha_green and is_macd_bullish:
            sigs.append(f"法則6:60MA突破(買) ★最強転換 {rsi_txt}")
        return sigs
    except: return []

# --- 監視メイン ---
now = datetime.now().time()
if dt_time(9, 20) <= now <= dt_time(15, 20):
    watch_data = load_watchlist()
    if watch_data:
        st.info(f"🚀 精密監視中... ({len(watch_data)}銘柄)")
        for item in watch_data:
            try:
                # データ取得 (MultiIndex対策)
                raw_df = yf.download(item['ticker'], period="5d", interval="1m", progress=False)
                if raw_df.empty: continue
                df = raw_df.copy()
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                
                if len(df) < 200: continue
                
                # 指標計算
                df['MA60'] = ta.sma(df['Close'], length=60)
                df['MA200'] = ta.sma(df['Close'], length=200)
                bb = ta.bbands(df['Close'], length=20, std=2)
                bb3 = ta.bbands(df['Close'], length=20, std=3)
                if bb is None or bb3 is None: continue
                
                df['BB_up_2'] = bb['BBU_20_2.0']
                df['BB_low_3'] = bb3['BBL_20_3.0']
                macd = ta.macd(df['Close'])
                df['MACD'] = macd['MACD_12_26_9']; df['MACD_S'] = macd['MACDs_12_26_9']
                df['VOL_MA'] = ta.sma(df['Volume'], length=20); df['RSI'] = ta.rsi(df['Close'], length=14)
                ha = ta.ha(df['Open'], df['High'], df['Low'], df['Close'])
                df['HA_O'] = ha['HA_open']; df['HA_C'] = ha['HA_close']
                
                sigs = check_laws(df, item['ticker'])
                for s in sigs: send_discord(f"🔔 **{item['ticker']} {JPX400_DICT.get(item['ticker'])}**\n{s}")
            except Exception as e:
                continue # 個別銘柄のエラーは無視して次へ
        time.sleep(180); st.rerun()
else:
    st.warning("🕒 監視時間外です。10秒後に停止します。")
    time.sleep(10); st.stop()
