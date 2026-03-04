import streamlit as st
import json
import os
import yfinance as yf
import pandas as pd
import requests

# --- 設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

st.set_page_config(page_title="Jack株AI：司令塔", layout="wide")

def calculate_rsi(series, period=14):
    delta = series.diff(); gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- 監視状況の取得 ---
def fetch_monitor_status(ticker):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        c = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        ma60 = c.rolling(60).mean()
        rsi_val = calculate_rsi(c, 14).iloc[-1]
        now_p = float(c.iloc[-1]); m60 = ma60.iloc[-1]
        diff60 = ((now_p / m60) - 1) * 100
        return [now_p, round(rsi_val, 1), round(diff60, 2), "監視中"]
    except:
        return [0.0, 0.0, 0.0, "待機中"]

st.title("📊 リアルタイム監視状況 (RSI対応版)")

if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if watchlist:
        rows = []
        for item in watchlist:
            res = fetch_monitor_status(item['ticker'])
            rows.append([item['name'], item['ticker']] + res)
        df_display = pd.DataFrame(rows, columns=["銘柄名", "コード", "現在値", "RSI", "MA60乖離", "状況"])
        st.dataframe(df_display.style.highlight_between(left=0, right=30, subset=['RSI'], color='#e1f5fe'), use_container_width=True)

st.divider()

# --- スキャン結果 ---
st.header("✨ お宝スキャン結果")
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.info(f"📅 スキャン日: {data.get('date', '不明')}")
    
    hits = data.get('hits', {})
    selected = []
    keys = list(hits.keys())
    
    for i in range(0, len(keys), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(keys):
                t = keys[i + j]
                info = hits[t]
                # ✅ 修正：infoが辞書じゃない場合のガード
                name = info.get('name', t) if isinstance(info, dict) else t
                reason = info.get('reason', '') if isinstance(info, dict) else info
                with cols[j]:
                    if st.checkbox(f"**{name}** ({t})\n{reason}", key=f"sel_{t}"):
                        selected.append({"ticker": t, "name": name})
    
    if st.button("💾 監視を開始する", type="primary", use_container_width=True):
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(selected, f, ensure_ascii=False, indent=2)
        st.success("リストを更新しました。")
        st.balloons()

