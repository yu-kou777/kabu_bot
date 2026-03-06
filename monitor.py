import streamlit as st
import pandas as pd
import os

st.title("📂 Jack株AI：過去のスキャン履歴")

if os.path.exists("scan_history.csv"):
    df_history = pd.read_csv("scan_history.csv")
    # 日付でソート（新しい順）
    df_history = df_history.sort_values("date", ascending=False)
    
    st.write(f"合計 {len(df_history)} 件のデータが見つかりました。")
    st.dataframe(df_history, use_container_width=True)
else:
    st.info("まだ履歴データがありません。スキャンを実行してください。")
