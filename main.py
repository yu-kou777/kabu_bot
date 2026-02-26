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

# --- 判定ロジック：トレンド・バイアス対応 ---
def check_laws(df, ticker):
    last = df.iloc[-1]; prev = df.iloc[-2]; sigs = []
    ma60 = last['MA60']; ma200 = last['MA200']
    
    # トレンド判定
    is_strong_down = ma200 > ma60  # 200MAが60MAより上（強い下降）
    is_strong_up = ma60 > ma200    # 60MAが200MAより上（強い上昇）
    
    is_ha_green = last['HA_C'] > last['HA_O']
    is_macd_bullish = last['MACD'] > last['MACD_S']
    is_vol_spike = last['Volume'] > last['VOL_MA'] * 1.5
    rsi_txt = f"(RSI:{last['RSI']:.1f})"

    # 1. 60MA上 & BB+2σ 3回接触 -> 売
    if last['Close'] > ma60 and (df['High'].tail(10) >= df['BB_up_2'].tail(10)).sum() >= 3:
        sigs.append(f"法則1:強気限界(売) {rsi_txt}")

    # 2. 60MA上 & 60MA反発 -> 買
    if last['Close'] > ma60 and last['Low'] <= ma60 and is_ha_green:
        sigs.append(f"法則2:60MA反発(買) {rsi_txt}")

    # 3. 200MA抵抗 (下降トレンド中の戻り売り急所)
    if is_strong_down and last['High'] >= ma200:
        sigs.append(f"💎【王道】法則3:200MA抵抗(売) - 絶好の売り場 {rsi_txt}")

    # 4. 60MA下 & BB-3σ接触 (下降トレンド時は抑制)
    if last['Close'] < ma60 and last['Low'] <= last['BB_low_3']:
        if is_strong_down:
            # 強下降トレンド時は、平均足の陽転がない限り通知を控えるか警告を出す
            prefix = "⚠️【逆張り注意】" if not is_ha_green else "🔥【短期リバ】"
            sigs.append(f"{prefix}法則4:BB-3σ接触(買) {rsi_txt}")
        else:
            sigs.append(f"法則4:BB-3σ反発(買) {rsi_txt}")

    # 6. 60MA下 & 60MA反発 -> 売 (住友鉱山の教訓：これを強調)
    if last['Close'] < ma60 and last['High'] >= ma60:
        prefix = "💎【王道】" if is_strong_down else ""
        sigs.append(f"{prefix}法則6:60MA反発(売) - 戻り売り {rsi_txt}")

    # 6. 60MA突破 -> 買 (上昇トレンドへの転換)
    if last['Close'] > ma60 and prev['Close'] < ma60 and is_ha_green and is_macd_bullish:
        sigs.append(f"法則6:60MA突破(買) ★最強転換 {rsi_txt}")

    return sigs

# --- メイン実行部 (自動監視) ---
now = datetime.now().time()
if dt_time(9, 20) <= now <= dt_time(15, 20):
    watch_data = load_watchlist()
    if watch_data:
        st.info(f"🚀 精密監視中... ({len(watch_data)}銘柄)")
        for item in watch_data:
            df = yf.download(item['ticker'], period="5d", interval="1m", progress=False)
            if df.empty or len(df) < 60: continue
            # 指標計算
            df['MA60'] = ta.sma(df['Close'], length=60); df['MA200'] = ta.sma(df['Close'], length=200)
            bb = ta.bbands(df['Close'], length=20, std=2); df['BB_up_2'] = bb['BBU_20_2.0']
            bb3 = ta.bbands(df['Close'], length=20, std=3); df['BB_low_3'] = bb3['BBL_20_3.0']
            macd = ta.macd(df['Close']); df['MACD'] = macd['MACD_12_26_9']; df['MACD_S'] = macd['MACDs_12_26_9']
            df['VOL_MA'] = ta.sma(df['Volume'], length=20); df['RSI'] = ta.rsi(df['Close'], length=14)
            ha = ta.ha(df['Open'], df['High'], df['Low'], df['Close'])
            df['HA_O'] = ha['HA_open']; df['HA_C'] = ha['HA_close']
            
            sigs = check_laws(df, item['ticker'])
            for s in sigs: send_discord(f"🔔 **{item['ticker']} {JPX400_DICT.get(item['ticker'])}**\n{s}")
        time.sleep(180); st.rerun()
else:
    st.warning("🕒 監視時間外です。10秒後に停止します。")
    time.sleep(10); st.stop()
