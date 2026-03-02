import streamlit as st
import json
import os
from datetime import datetime

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI：事前検知ビューア", layout="wide")

st.title("☀️ 本日の事前スキャン結果")

if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    st.info(f"📅 スキャン実施日: {data['date']} (プライム全件)")
    
    hit_list = list(data['hits'].keys())
    if not hit_list:
        st.write("本日の条件合致銘柄はありません。")
    else:
        # 見つかった銘柄を選択肢として表示
        selected = st.multiselect("監視を開始する銘柄を選択してください", hit_list, default=hit_list)
        
        if st.button("💾 選択した銘柄で5分おき監視を確定", type="primary"):
            final_data = [{"ticker": t, "reason": data['hits'][t]} for t in selected]
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            st.success(f"✅ {len(final_data)} 銘柄を監視リストに入れました。monitor.pyが予測を開始します。")

else:
    st.warning("事前スキャンデータが見つかりません。09:15の自動実行を待つか、monitor.pyを起動してください。")
