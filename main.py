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

st.set_page_config(page_title="Jack株AI：ダッシュボード", layout="wide")

def calculate_rsi(series, period=14):
    delta = series.diff(); gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

# --- 監視状況の取得関数 ---
def fetch_monitor_status(ticker):
    try:
        # RSI計算用に余裕を持ってデータを取得
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        c = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        ma60 = c.rolling(60).mean(); ma200 = c.rolling(200).mean()
        rsi_val = calculate_rsi(c, 14).iloc[-1]
        
        now_p = float(c.iloc[-1]); m60 = ma60.iloc[-1]; m200 = ma200.iloc[-1]
        diff60 = ((now_p / m60) - 1) * 100
        
        status = "静観中"
        if rsi_val <= 30: status = "🔥底圏狙い"
        if rsi_val >= 70: status = "⚠️天井圏警戒"
        if abs(diff60) < 0.1: status = "💎法則2近接"
        
        return [f"{now_p:,.1f}", f"{rsi_val:.1f}", f"{diff60:+.2f}%", status]
    except:
        return ["-", "-", "-", "データ待機中"]

# --- メイン画面 ---
st.title("📊 リアルタイム監視状況 (RSI対応版)")

if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    
    if watchlist:
        rows = []
        for item in watchlist:
            res = fetch_monitor_status(item['ticker'])
            rows.append([item['name'], item['ticker']] + res)
        
        df_display = pd.DataFrame(rows, columns=["銘柄名", "コード", "現在値", "RSI", "MA60乖離", "ステータス"])
        
        # 色付けのルール（RSIの過熱感など）
        st.dataframe(df_display.style.highlight_between(left=0, right=30, subset=['RSI'], color='#e1f5fe')
                                     .highlight_between(left=70, right=100, subset=['RSI'], color='#ffebee'),
                     use_container_width=True)
    else:
        st.info("監視リストに銘柄が登録されていません。")

st.divider()

# --- スキャン結果 ＆ 登録 ---
st.header("✨ お宝スキャン結果")
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.caption(f"最終スキャン日: {data['date']}")
    
    hits = data['hits']
    selected = []
    cols = st.columns(3)
    for i, (t, info) in enumerate(hits.items()):
        with cols[i % 3]:
            name = info.get('name', t)
            if st.checkbox(f"**{name}** ({t})\n{info.get('reason','')}", key=f"sel_{t}"):
                selected.append({"ticker": t, "name": name})
    
    if st.button("💾 監視を開始する", type="primary", use_container_width=True):
        if selected:
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(selected, f, ensure_ascii=False, indent=2)
            requests.post(DISCORD_URL, json={"content": f"✅ **【監視リスト更新】** {len(selected)}銘柄の監視を開始しました。"})
            st.success("監視を開始しました！")
            st.balloons()
