import streamlit as st
import json
import os

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI：テスト窓", layout="wide")
st.title("🧪 テスト：事前スキャン結果")

if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.info(f"📅 更新日: {data['date']}")
    hits = data['hits']
    selected = st.multiselect("監視対象を選択", list(hits.keys()), default=list(hits.keys()))
    if st.button("💾 監視リストを保存", type="primary"):
        final = [{"ticker": t, "reason": hits[t]} for t in selected]
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(final, f, ensure_ascii=False, indent=2)
        st.success("テスト用リストを保存しました。")
else:
    st.warning("スキャン結果ファイルがありません。GitHub Actionsを動かしてください。")
