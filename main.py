import streamlit as st
import json
import os
import requests

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

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
        selected = []
        for t, info in hits.items():
            name = info.get('name', t)
            if st.checkbox(f"**{name}** ({t}) | {info.get('reason','')}", key=t):
                selected.append({"ticker": t, "name": name})
        
        if st.button("💾 選択した銘柄でリアルタイム監視を開始", type="primary", use_container_width=True):
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(selected, f, ensure_ascii=False, indent=2)
            
            # ✅ Discordへ即時通知
            names = "、".join([s['name'] for s in selected])
            requests.post(DISCORD_URL, json={"content": f"✅ **【監視リスト更新】**\n以下の銘柄の監視を受け付けました：\n`{names}`"})
            
            st.success("監視を開始しました。Discordを確認してください！")
            st.balloons()
else:
    st.warning("スキャン結果がありません。朝08:45の自動実行をお待ちください。")
