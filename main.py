import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import time

# --- 設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

st.set_page_config(page_title="Jack株AI：理由別・統合監視パネル", layout="wide")

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

# --- RSI計算 ---
def get_latest_rsi(tickers, period="1mo"):
    data = yf.download(tickers, period=period, interval="1d", group_by='ticker', progress=False)
    results = {}
    for t in tickers:
        try:
            df = data[t].dropna()
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]
            results[t] = rsi
        except: continue
    return results

# --- UI：銘柄を探す・登録 ---
tab1, tab2 = st.tabs(["🌙 銘柄検索・一括登録", "☀️ 監視中の銘柄状況"])

with tab1:
    st.header("🌙 明日のための仕込みスキャナー")
    
    # 検索結果を一時保存する辞書 {ticker: reason}
    if 'temp_watchlist' not in st.session_state:
        st.session_state.temp_watchlist = {}

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("① 低RSI（逆張り狙い）")
        low_rsi_val = st.slider("低RSIしきい値", 10, 45, 35)
        if st.button("🔍 低RSI銘柄をスキャン"):
            rsi_data = get_latest_rsi(list(JPX400_DICT.keys()))
            for t, val in rsi_data.items():
                if val <= low_rsi_val:
                    st.session_state.temp_watchlist[t] = "低RSI銘柄"
            st.success("スキャン完了！下のリストに反映されました。")

    with col2:
        st.subheader("② RSI高騰・下落（過熱検知）")
        if st.button("🔍 RSI高騰・下落をスキャン"):
            rsi_data = get_latest_rsi(list(JPX400_DICT.keys()))
            for t, val in rsi_data.items():
                if val >= 75: st.session_state.temp_watchlist[t] = "RSI高騰"
                elif val <= 20: st.session_state.temp_watchlist[t] = "RSI下落(極)"
            st.success("スキャン完了！下のリストに反映されました。")

    st.write("---")
    st.subheader("✅ 監視リストの最終確認・手動追加")
    
    options = [f"{c} {n}" for c, n in JPX400_DICT.items()]
    # 現在の検索結果をデフォルトにする
    current_hits = [f"{t} {JPX400_DICT[t]}" for t in st.session_state.temp_watchlist.keys()]
    
    selected_full = st.multiselect("監視リスト（検索結果＋手動追加）", options, default=current_hits)
    
    if st.button("💾 この内容で監視を確定・保存"):
        final_list = []
        for full_name in selected_full:
            ticker = full_name.split(" ")[0]
            # 理由を特定
            reason = st.session_state.temp_watchlist.get(ticker, "手動追加")
            final_list.append({
                "ticker": ticker,
                "name": JPX400_DICT[ticker],
                "reason": reason,
                "added_at": get_jst_now().strftime('%Y-%m-%d %H:%M')
            })
        
        with open(WATCHLIST_FILE, 'w') as f:
            json.dump(final_list, f)
        st.success(f"【成功】{len(final_list)}銘柄を理由付きで保存しました！")
        # リセット
        st.session_state.temp_watchlist = {}

with tab2:
    st.header("☀️ 監視中の銘柄")
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r') as f:
            watch_data = json.load(f)
        
        if watch_data:
            # 理由別に分かりやすく表示
            for item in watch_data:
                reason_color = "🔴" if "高騰" in item['reason'] else "🔵" if "RSI" in item['reason'] else "⚪"
                st.write(f"{reason_color} **{item['ticker']} {item['name']}**")
                st.caption(f"監視理由: {item['reason']} / 登録日時: {item['added_at']}")
                st.write("---")
        else:
            st.warning("現在監視中の銘柄はありません。")
