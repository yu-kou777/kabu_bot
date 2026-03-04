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

# --- 監視状況の取得関数 ---
def fetch_monitor_status(ticker):
    try:
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        c = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        ma60, ma200 = c.rolling(60).mean(), c.rolling(200).mean()
        now_p = float(c.iloc[-1]); m60 = ma60.iloc[-1]; m200 = ma200.iloc[-1]
        
        diff60 = ((now_p / m60) - 1) * 100
        diff200 = ((now_p / m200) - 1) * 100
        
        status = "静観中"
        if abs(diff60) < 0.1: status = "💎法則2/6近接"
        if abs(diff200) < 0.1: status = "💎法則3/5近接"
        
        return [f"{now_p:,.1f}", f"{diff60:+.2f}%", f"{diff200:+.2f}%", status]
    except:
        return ["-", "-", "-", "データ待機中"]

# --- メイン画面 ---
st.title("📊 リアルタイム監視状況")

if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    
    if watchlist:
        rows = []
        for item in watchlist:
            res = fetch_monitor_status(item['ticker'])
            rows.append([item['name'], item['ticker']] + res)
        
        df_display = pd.DataFrame(rows, columns=["銘柄名", "コード", "現在値", "MA60乖離", "MA200乖離", "ステータス"])
        st.dataframe(df_display, use_container_width=True)
    else:
        st.info("監視リストに銘柄が登録されていません。下から追加してください。")

st.divider()

# --- スキャン結果 ＆ 登録 ---
st.header("✨ お宝スキャン結果")
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.caption(f"最終スキャン完了時刻: {data['date']}")
    
    hits = data['hits']
    selected = []
    cols = st.columns(3)
    for i, (t, info) in enumerate(hits.items()):
        with cols[i % 3]:
            name = info.get('name', t)
            if st.checkbox(f"**{name}** ({t})\n{info.get('reason','')}", key=f"sel_{t}"):
                selected.append({"ticker": t, "name": name})
    
    if st.button("💾 選択した銘柄で監視を開始する", type="primary", use_container_width=True):
        if selected:
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(selected, f, ensure_ascii=False, indent=2)
            requests.post(DISCORD_URL, json={"content": f"✅ **【監視リスト更新】** {len(selected)}銘柄の監視を開始しました。"})
            st.success("GitHubへ指示を送りました！")
            st.balloons()
else:
    st.warning("スキャン結果がありません。朝08:45の自動実行を待つか、GitHubで手動実行してください。")
