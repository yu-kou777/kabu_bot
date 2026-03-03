import streamlit as st
import json
import os
import yfinance as yf

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI：全市場スキャナー", layout="wide")
st.title("🚀 プライム市場1,600社 全件スキャン結果")

@st.cache_data
def get_stock_name(ticker):
    try:
        t = yf.Ticker(ticker)
        return t.info.get('shortName', ticker)
    except:
        return ticker

if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.info(f"📅 更新日: {data['date']}")
    
    hits = data['hits']
    if not hits:
        st.write("現在、極端な異常値を検知した銘柄はありません。")
    else:
        st.subheader(f"💎 本日のお宝候補 ({len(hits)}件)")
        
        # 銘柄リストを整形して表示
        selected = []
        for t, reason in hits.items():
            name = get_stock_name(t)
            col1, col2 = st.columns([3, 1])
            with col1:
                is_checked = st.checkbox(f"**{name}** ({t}) - {reason}", key=t)
                if is_checked:
                    selected.append({"ticker": t, "name": name})
        
        if st.button("💾 選択した銘柄のリアルタイム監視を開始", type="primary"):
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(selected, f, ensure_ascii=False, indent=2)
            st.success("GitHubへ監視指示を送信しました！")
            st.balloons()
else:
    st.warning("スキャン結果がありません。朝9:10の自動実行をお待ちください。")
