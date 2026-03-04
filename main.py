import streamlit as st
import json
import os
import yfinance as yf
import pandas as pd
import time
import io
import requests
import numpy as np

# --- ⚙️ 基本設定 ---
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"
# JPXの統計データURL
JPX_LIST_URL = "https://www.jpx.co.jp/markets/statistics-banner/quote/tvdivq0000001vg2-att/data_j.xls"
# 💡 ブロック回避用の高度なヘッダー
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
}

st.set_page_config(page_title="Jack株AI：司令塔", layout="wide")

def calculate_rsi(series, period=14):
    if len(series) < period: return pd.Series([np.nan] * len(series))
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 📡 プライム市場スキャン実行 ---
def run_prime_scan(price_limit):
    status_box = st.empty()
    status_box.info("🚀 JPXからプライム銘柄リストを取得中（ステルスモード）...")
    
    name_map = {}
    try:
        # 💡 セッションを使用してクッキー等をシミュレート
        session = requests.Session()
        res = session.get(JPX_LIST_URL, headers=HEADERS, timeout=30)
        
        # HTMLが返ってきていないかチェック
        if res.content.startswith(b'<!DOCTYPE') or res.status_code != 200:
            raise ValueError("JPXから拒否されました（HTMLが返されました）")
            
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        prime_df = df[df['市場・商品区分'].str.contains('プライム|Prime', na=False)]
        name_map = {f"{int(row['コード'])}.T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        st.warning(f"⚠️ JPX直接取得に失敗。主要銘柄リストで代替します。({e})")
        # バックアップ用：主要な高価格帯銘柄を含むリスト
        name_map = {
            "7203.T":"トヨタ", "9432.T":"NTT", "9984.T":"SBG", "6758.T":"ソニーG", "8306.T":"三菱UFJ",
            "8035.T":"東エレク", "6098.T":"リクルート", "4502.T":"武田", "2502.T":"アサヒ", "5401.T":"日本製鉄",
            "7267.T":"ホンダ", "9020.T":"JR東日本", "9433.T":"KDDI", "4063.T":"信越化", "6501.T":"日立",
            "6954.T":"ファナック", "4519.T":"中外薬", "6273.T":"SMC", "6367.T":"ダイキン", "3382.T":"7&i",
            "8001.T":"伊藤忠", "8058.T":"三菱商", "4503.T":"アステラス", "6723.T":"ルネサス", "6857.T":"アドバンテ"
        }

    tickers = list(name_map.keys())
    hits = {}
    progress_bar = st.progress(0)
    
    batch_size = 40 # 💡 負荷を抑えるために小分けに
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        status_box.text(f"📊 分析中: {i} / {len(tickers)} 銘柄完了... (現在ヒット: {len(hits)}件)")
        
        try:
            # 高速化のため期間を1ヶ月に限定
            data = yf.download(batch, period="1mo", interval="1d", progress=False, threads=False)
            close_data = data['Close'] if 'Close' in data else data
            
            for t in batch:
                try:
                    c = close_data[t].dropna() if isinstance(close_data, pd.DataFrame) else close_data.dropna()
                    if c.empty: continue
                    
                    # ✅ 株価3000円以上条件
                    current_price = float(c.iloc[-1])
                    if current_price < price_limit: continue
                    
                    rsi_val = calculate_rsi(c, 14).iloc[-1]
                    
                    # RSI判定（底打ち/過熱）
                    if not np.isnan(rsi_val) and (rsi_val <= 30 or rsi_val >= 70):
                        hits[t] = {
                            "name": name_map[t], 
                            "price": current_price,
                            "rsi": round(rsi_val, 1)
                        }
                except: continue
        except: pass
        
        progress_bar.progress(min((i + batch_size) / len(tickers), 1.0))
        time.sleep(1.5)

    result_data = {"date": time.strftime('%Y-%m-%d %H:%M'), "hits": hits}
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    status_box.success(f"✨ スキャン完了！ {len(hits)}件検知。")
    st.balloons()
    return hits

# --- 🖥️ ダッシュボード ---
st.title("📊 プライム司令塔ダッシュボード")

st.sidebar.header("🔍 スキャン設定")
price_min = st.sidebar.number_input("最小株価条件 (円)", value=3000, step=500)
if st.sidebar.button("🚀 プライム市場スキャンを開始"):
    run_prime_scan(price_min)

auto_refresh = st.sidebar.toggle("⏱️ 画面自動更新 (1分)", value=False)

if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if watchlist:
        st.subheader("📋 現在の監視銘柄（リアルタイム）")
        rows = []
        for item in watchlist:
            try:
                d = yf.download(item['ticker'], period="1d", interval="1m", progress=False)
                c = d['Close'].iloc[:,0] if isinstance(d['Close'], pd.DataFrame) else d['Close']
                now_p = float(c.iloc[-1])
                now_rsi = calculate_rsi(c, 14).iloc[-1]
                rows.append([item['name'], item['ticker'], f"{now_p:,.1f}", f"{now_rsi:.1f}"])
            except: rows.append([item['name'], item['ticker'], "取得中", "-"])
        st.table(pd.DataFrame(rows, columns=["銘柄名", "コード", "価格", "RSI(1分)"]))

st.divider()

st.header(f"✨ 条件合致銘柄 ({price_min:,.0f}円以上)")
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        scan_results = json.load(f)
    st.caption(f"📅 最終スキャン：{scan_results.get('date', '不明')}")
    hits = scan_results.get('hits', {})
    
    if not hits:
        st.write("条件に合う銘柄は見つかりませんでした。")
    else:
        selected = []
        keys = list(hits.keys())
        for i in range(0, len(keys), 3):
            cols = st.columns(3)
            for j in range(3):
                if i+j < len(keys):
                    t = keys[i+j]
                    info = hits[t]
                    with cols[j]:
                        if st.checkbox(f"**{info['name']}** ({t})\n{info['price']:,.0f}円 / RSI:{info['rsi']}", key=f"sel_{t}"):
                            selected.append({"ticker": t, "name": info['name']})
        
        if st.button("💾 選択した銘柄を保存", type="primary", use_container_width=True):
            with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
                json.dump(selected, f, ensure_ascii=False, indent=2)
            st.success("保存完了！")

if auto_refresh:
    time.sleep(60)
    st.rerun()
