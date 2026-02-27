import streamlit as st
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone
import numpy as np

# --- 設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
AUTO_LIST_FILE = "auto_scan_list.json"

# ✅ プライム主力銘柄（圧縮記述方式）
# ※ここに「コード:銘柄名,コード:銘柄名...」の形式でカンマ区切りで追加すれば何百銘柄でも一瞬で読み込めます
PRIME_CSV = "1605.T:INPEX,1801.T:大成建設,1802.T:大林組,1925.T:大和ハウス,2502.T:アサヒ,2802.T:味の素,2914.T:JT,4063.T:信越化学,4502.T:武田薬品,4503.T:アステラス,4519.T:中外製薬,4568.T:第一三共,4901.T:富士フイルム,5401.T:日本製鉄,5713.T:住友鉱山,6301.T:小松製作所,6367.T:ダイキン,6501.T:日立,6758.T:ソニーG,6857.T:アドバンテスト,6920.T:レーザーテック,6954.T:ファナック,6981.T:村田製作所,7203.T:トヨタ,7267.T:ホンダ,7741.T:HOYA,7974.T:任天堂,8001.T:伊藤忠,8031.T:三井物産,8035.T:東京エレクトロン,8058.T:三菱商事,8306.T:三菱UFJ,8316.T:三井住友,8411.T:みずほFG,8766.T:東京海上,8801.T:三井不動産,9020.T:JR東日本,9101.T:日本郵船,9104.T:商船三井,9432.T:NTT,9433.T:KDDI,9983.T:ファーストリテイリング,9984.T:ソフトバンクG,6098.T:リクルート,4689.T:LINEヤフー,4307.T:野村総研,3382.T:セブン&アイ,4523.T:エーザイ,4578.T:大塚HD,6902.T:デンソー,7269.T:スズキ,8604.T:野村HD"

# CSV文字列を辞書に変換
PRIME_DICT = {x.split(':')[0]: x.split(':')[1] for x in PRIME_CSV.split(',')}

st.set_page_config(page_title="Jack株AI：プライム高速版", layout="wide")

if 'ms1' not in st.session_state: st.session_state.ms1 = []
if 'ms2' not in st.session_state: st.session_state.ms2 = []
if 'reasons' not in st.session_state: st.session_state.reasons = {}

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(series):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    return 100 - (100 / (1 + (gain / loss)))

def calculate_rci(series, period=9):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

def save_manual_list(selected_list):
    final_data = []
    for full in selected_list:
        code = full.split(" ")[0]
        final_data.append({
            "ticker": code,
            "name": PRIME_DICT.get(code, ""),
            "reason": st.session_state.reasons.get(code, "手動登録"),
            "at": get_jst_now().strftime('%m/%d %H:%M')
        })
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    st.success(f"✅ {len(final_data)} 銘柄を監視リストに保存しました！")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 5日RSI検索", "📊 複合検索", "🤖 15時自動検知", "📋 全監視リスト"])
options = [f"{k} {v}" for k, v in PRIME_DICT.items()]
tickers_list = list(PRIME_DICT.keys())

with tab1:
    st.header("🌙 直近5日間のRSI底打ち検知")
    thr1 = st.slider("しきい値(RSI)", 10, 80, 60, key="s1")
    
    if st.button("🚀 超高速スキャン開始", key="b1"):
        log_area = st.expander("📝 スキャンログ", expanded=True)
        hits_temp = []
        bar = st.progress(0)
        status = st.empty()
        
        try:
            status.text("📡 全銘柄のデータを一括ダウンロード中...（数秒お待ちください）")
            # ✅ 一括ダウンロード（ここで劇的な高速化を実現）
            df = yf.download(tickers_list, period="3mo", progress=False)
            
            for i, (t, n) in enumerate(PRIME_DICT.items()):
                bar.progress((i+1)/len(PRIME_DICT))
                try:
                    # MultiIndexから各銘柄の終値を抽出
                    close = df['Close'][t].dropna() if len(tickers_list) > 1 else df['Close'].dropna()
                    if len(close) < 15: continue
                    
                    min_rsi = calculate_rsi(close).tail(5).min()
                    if min_rsi <= thr1:
                        hits_temp.append(f"{t} {n}")
                        st.session_state.reasons[t] = f"5日RSI低迷({min_rsi:.1f})"
                        log_area.write(f"✅ **{t} {n}** ヒット! (最小RSI: {min_rsi:.1f})")
                    else:
                        log_area.write(f"⚪ スルー: {t} {n} (RSI: {min_rsi:.1f})")
                except Exception as e:
                    log_area.write(f"❌ {t} {n}: エラー")
        except Exception as e:
            st.error(f"データ取得エラー: {e}")
            
        status.empty(); bar.empty()
        st.session_state.ms1 = hits_temp

    sel1 = st.multiselect("監視に追加", options, key="ms1")
    if st.button("💾 手動リストを保存", key="sv1"): save_manual_list(sel1)

with tab2:
    st.header("📊 RSI×RCI 複合狙い撃ち")
    if st.button("🔍 超高速複合スキャン開始", key="b2"):
        log_area2 = st.expander("📝 複合スキャンログ", expanded=True)
        hits_temp_comp = []
        bar2 = st.progress(0); status2 = st.empty()
        
        try:
            status2.text("📡 全銘柄のデータを一括ダウンロード中...")
            df = yf.download(tickers_list, period="4mo", progress=False)
            
            for i, (t, n) in enumerate(PRIME_DICT.items()):
                bar2.progress((i+1)/len(PRIME_DICT))
                try:
                    close = df['Close'][t].dropna() if len(tickers_list) > 1 else df['Close'].dropna()
                    if len(close) < 15: continue
                    
                    rv = calculate_rsi(close).iloc[-1]
                    rcv = calculate_rci(close).iloc[-1]
                    
                    if (rv <= 35 and rcv <= -80):
                        hits_temp_comp.append(f"{t} {n}")
                        st.session_state.reasons[t] = f"大底(RSI:{rv:.1f}, RCI:{rcv:.1f})"
                        log_area2.write(f"✅ **{t} {n}** 大底!")
                    elif (rv >= 75 and rcv >= 80):
                        hits_temp_comp.append(f"{t} {n}")
                        st.session_state.reasons[t] = f"天井(RSI:{rv:.1f}, RCI:{rcv:.1f})"
                        log_area2.write(f"✅ **{t} {n}** 天井!")
                    else:
                        log_area2.write(f"⚪ スルー: {t} {n}")
                except Exception as e: pass
        except Exception as e: st.error(f"エラー: {e}")
                
        status2.empty(); bar2.empty()
        st.session_state.ms2 = hits_temp_comp

    sel2 = st.multiselect("監視に追加(複合)", options, key="ms2")
    if st.button("💾 手動リストを保存(複合結果)", key="sv2"): save_manual_list(sel2)

with tab3:
    st.header("🤖 15:00 AI自動検知結果")
    if os.path.exists(AUTO_LIST_FILE):
        with open(AUTO_LIST_FILE, 'r', encoding='utf-8') as f:
            auto_data = json.load(f)
            if auto_data:
                for item in auto_data:
                    st.write(f"✅ **{item['ticker']} {item['name']}** ({item['reason']})")
            else: st.info("現在、自動検知銘柄はありません。")
    else: st.info("15時のスキャン後にここに表示されます。")

with tab4:
    st.header("📋 監視リスト（1分足監視対象）")
    for label, path in [("【手動登録】", WATCHLIST_FILE), ("【15時自動】", AUTO_LIST_FILE)]:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                st.subheader(label)
                if not data: st.write("銘柄なし")
                for i in data: st.write(f"🔹 {i['ticker']} {i['name']} ({i['reason']})")
