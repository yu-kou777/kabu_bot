import streamlit as st
import json
import os
from datetime import datetime

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI：朝の結果確認", layout="wide")
st.title("☀️ 今朝のプライム全件検知")

if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    st.success(f"📅 スキャン日: {data['date']} (完了)")
    hits = data['hits']
    
    if not hits:
        st.write("条件に合う銘柄はありませんでした。")
    else:
        st.write(f"🔍 **{len(hits)} 銘柄**が見つかりました。")
        selected = st.multiselect("監視を開始する銘柄を選択", list(hits.keys()), default=list(hits.keys()))
        
        if st.button("💾 この銘柄で5分おき監視を確定", type="primary", use_container_width=True):
            # 銘柄名を保持する（必要なら）
            final = [{"ticker": t, "reason": hits[t]} for t in selected]
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(final, f, ensure_ascii=False, indent=2)
            st.balloons()
            st.success("確定しました！Discordで通知が始まります。")
else:
    st.info("09:15のスキャン完了までお待ちください。")
