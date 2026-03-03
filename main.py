import streamlit as st
import json
import os

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

st.set_page_config(page_title="Jack株AI", layout="wide")
st.title("🚀 プライム市場1,600社 全件スキャン")

if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.info(f"📅 スキャン日: {data['date']}")
    
    hits = data['hits']
    if not hits:
        st.write("現在、異常値を検知した銘柄はありません。")
    else:
        st.subheader(f"💎 本日のお宝候補 ({len(hits)}件)")
        selected = []
        for t, info in hits.items():
            # ✅ 修正：データが古い形式（文字列）でもエラーにならないようにガード
            if isinstance(info, dict):
                name = info.get('name', t)
                reason = info.get('reason', '')
            else:
                name = t
                reason = info # 古い形式の場合は文字をそのまま理由にする
            
            if st.checkbox(f"**{name}** ({t}) | {reason}", key=t):
                selected.append({"ticker": t, "name": name})
        
        if st.button("💾 選択した銘柄でリアルタイム監視を開始", type="primary", use_container_width=True):
            if selected:
                with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                    json.dump(selected, f, ensure_ascii=False, indent=2)
                st.success("監視を開始しました！Discordを確認してください。")
                st.balloons()
            else:
                st.warning("銘柄を選択してください。")
else:
    st.warning("スキャン結果がありません。朝08:45の自動実行をお待ちください。")
