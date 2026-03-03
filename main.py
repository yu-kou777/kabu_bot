import streamlit as st
import json
import os

WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"

# 銘柄名辞書
TICKER_NAMES = {
    "2502.T": "アサヒ", "5401.T": "日本製鉄", "7267.T": "ホンダ",
    "9020.T": "JR東日本", "9432.T": "NTT", "9433.T": "KDDI",
    "1605.T": "INPEX", "7203.T": "トヨタ", "8035.T": "東エレク", "9984.T": "SBG"
}

st.set_page_config(page_title="Jack株AI：ダッシュボード", layout="wide")
st.title("☀️ 今朝の事前スキャン結果")

if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    st.info(f"📅 更新日: {data['date']}")
    
    hits = data['hits']
    if not hits:
        st.write("現在、条件に合う銘柄はありません。")
    else:
        # ✅ 修正：表示を和名にするための設定
        def get_label(ticker):
            name = TICKER_NAMES.get(ticker, "不明")
            return f"{name} ({ticker})"

        selected_tickers = st.multiselect(
            "監視を開始する銘柄を選択（複数可）", 
            options=list(hits.keys()),
            default=list(hits.keys()),
            format_func=get_label # ここで表示を日本語に変換
        )
        
        if st.button("💾 監視リストを保存して開始", type="primary", use_container_width=True):
            final = [{"ticker": t, "name": TICKER_NAMES.get(t, t)} for t in selected_tickers]
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(final, f, ensure_ascii=False, indent=2)
            st.balloons()
            st.success("GitHubへ保存しました。5分以内に監視が始まります。")
else:
    st.warning("スキャン結果がありません。GitHub Actionsの完了をお待ちください。")
