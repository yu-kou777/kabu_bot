import streamlit as st
import json
import os

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI：ダッシュボード", layout="wide")
st.title("☀️ 今朝の事前検知結果")

if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.success(f"📅 データ更新日: {data['date']}")
    
    selected = st.multiselect("監視対象を選択", list(data['hits'].keys()), default=list(data['hits'].keys()))
    
    if st.button("💾 監視リストを保存してGitHubへ反映", type="primary"):
        final = [{"ticker": t, "reason": data['hits'][t]} for t in selected]
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(final, f, ensure_ascii=False, indent=2)
        st.info("保存完了。次のGitHub Actionsの実行で監視が始まります。")
else:
    st.warning("スキャンデータがありません。09:15の実行をお待ちください。")
