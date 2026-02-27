import streamlit as st
import json
import os

# --- 設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
AUTO_LIST_FILE = "auto_scan_list.json" # AIが15時に見つけた銘柄用

st.set_page_config(page_title="Jack株AI：二系統管理", layout="wide")

# --- UI ---
tab1, tab2, tab3 = st.tabs(["🔍 手動検索・登録", "🤖 15時自動検知リスト", "☀️ 全監視状況"])

with tab1:
    st.header("🌙 手動で監視銘柄を追加")
    # （これまでの検索・保存ロジック）
    st.write("ここで保存した銘柄は「手動監視」として扱われます。")

with tab2:
    st.header("🤖 15:00 AI自動検知（大底・天井）")
    if os.path.exists(AUTO_LIST_FILE):
        with open(AUTO_LIST_FILE, 'r', encoding='utf-8') as f:
            auto_data = json.load(f)
        if auto_data:
            st.success(f"本日 15:00 に {len(auto_data)} 銘柄を検知しました。")
            for item in auto_data:
                st.write(f"✅ **{item['ticker']} {item['name']}**")
                st.caption(f"理由: {item['reason']}")
                st.write("---")
        else:
            st.info("現在、自動検知された銘柄はありません。")
    else:
        st.info("15時のスキャン実行後にここに表示されます。")

with tab3:
    st.header("☀️ 現在の監視対象（合計）")
    # 両方のファイルを読み込んで表示
    lists = {"【手動】": WATCHLIST_FILE, "【15時自動】": AUTO_LIST_FILE}
    for label, path in lists.items():
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                st.subheader(label)
                for item in data:
                    st.write(f"🔹 {item['ticker']} {item['name']} ({item['reason']})")
