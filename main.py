import streamlit as st
import json
import os

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI：全市場スキャナー", layout="wide")
st.title("🚀 プライム市場1,600社 全件スキャン")

if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.info(f"📅 スキャン日: {data['date']}")
    
    hits = data['hits']
    if not hits:
        st.write("現在、極端な異常値を検知した銘柄はありません。")
    else:
        st.subheader(f"💎 本日のお宝候補 ({len(hits)}件)")
        selected = []
        for t, info in hits.items():
            name = info.get('name', t)
            reason = info.get('reason', '')
            # ✅ 保存された和名を表示
            if st.checkbox(f"**{name}** ({t}) | {reason}", key=t):
                selected.append({"ticker": t, "name": name})
        
        if st.button("💾 選択した銘柄でリアルタイム監視を開始", type="primary", use_container_width=True):
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(selected, f, ensure_ascii=False, indent=2)
            st.success("監視リストを更新しました。まもなくDiscord通知が始まります。")
            st.balloons()
else:
    st.warning("スキャン結果がありません。朝08:45の自動実行をお待ちください。")
