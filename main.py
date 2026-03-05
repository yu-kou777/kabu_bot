import streamlit as st
import json
import os
import yfinance as yf
import pandas as pd
import time
import numpy as np
import requests
from datetime import datetime, timedelta

# --- ⚙️ 基本設定 ---
# API Keyは環境から自動提供されるため空文字列で定義
const_apiKey = ""
WATCHLIST_FILE = "jack_watchlist.json"
PRE_SCAN_FILE = "pre_scan_results.json"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

st.set_page_config(page_title="Jack株AI：最終兵器", layout="wide")

# --- 📈 テクニカル計算関数 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_rci(series, period=9):
    def rci_func(x):
        n = len(x)
        d = np.array(range(n, 0, -1))
        r = pd.Series(x).rank(method='min').values
        return (1 - 6 * sum((d - r)**2) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

def get_dead_cross_info(df):
    """5日線が25日線を下抜けた最新の日付を特定"""
    ma5 = df['Close'].rolling(5).mean()
    ma25 = df['Close'].rolling(25).mean()
    # デッドクロス判定
    dc_series = (ma5 < ma25) & (ma5.shift(1) >= ma25.shift(1))
    dc_dates = dc_series[dc_series].index
    if not dc_dates.empty:
        return dc_dates[-1].strftime('%Y-%m-%d')
    return "なし"

# --- 🧠 AI分析エンジン (Gemini API) ---
def get_ai_insight(ticker, name, current_price, rsi, rci):
    """Gemini APIを使用して、変動要因、トレンド、上昇予想を行う"""
    system_prompt = "あなたは日本の株式市場に精通したAIアナリストです。提供されたテクニカルデータから、銘柄の性質、トレンド、将来予測を分析してください。"
    user_prompt = f"""
    銘柄: {name} ({ticker})
    現在株価: {current_price}円
    RSI(14): {rsi:.1f}
    RCI(9): {rci:.1f}
    
    以下の項目を厳密なJSON形式で答えてください：
    - driver: 変動要因（例：金価格、ドル円、米テック株指数、半導体需要など）
    - trend_direction: トレンドの向き（上昇/下降/横ばい）
    - forecast_date: 上昇が期待される予想日（YYYY-MM-DD）
    - forecast_price: 予想株価（数値）
    - comment: 短い助言
    """
    
    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "driver": {"type": "STRING"},
                    "trend_direction": {"type": "STRING"},
                    "forecast_date": {"type": "STRING"},
                    "forecast_price": {"type": "NUMBER"},
                    "comment": {"type": "STRING"}
                }
            }
        }
    }
    
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={const_apiKey}"
    
    # 指数バックオフによるリトライ
    for i in range(5):
        try:
            response = requests.post(api_url, json=payload, timeout=30)
            if response.status_code == 200:
                return json.loads(response.json()['candidates'][0]['content']['parts'][0]['text'])
            time.sleep(2 ** i)
        except:
            time.sleep(2 ** i)
    
    return {
        "driver": "データ取得エラー", "trend_direction": "不明",
        "forecast_date": "-", "forecast_price": 0, "comment": "APIリミットまたは接続エラー"
    }

# --- 📡 スキャンロジック ---
def run_ultimate_scan(price_min, vol_min):
    st.info("🚀 プライム市場の主要銘柄を全件AI精査中... (推定10-15分)")
    
    # JPXの代わりに主要高流動性銘柄リストをターゲットにする（確実性を優先）
    # ※本番ではここにさらに銘柄を追加して拡張可能
    target_stocks = {
        "8035.T": "東エレク", "9984.T": "SBG", "6758.T": "ソニーG", "7203.T": "トヨタ",
        "6920.T": "レーザーテク", "6857.T": "アドバンテ", "6146.T": "ディスコ", "6723.T": "ルネサス",
        "4063.T": "信越化", "6367.T": "ダイキン", "6273.T": "SMC", "7974.T": "任天堂",
        "8001.T": "伊藤忠", "8058.T": "三菱商", "8306.T": "三菱UFJ", "8316.T": "三井住友",
        "9101.T": "日本郵船", "9104.T": "商船三井", "9107.T": "川崎汽", "7011.T": "三菱重",
        "9432.T": "NTT", "9433.T": "KDDI", "9020.T": "JR東日本", "4502.T": "武田", "2502.T": "アサヒ"
    }

    hits = {}
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    tickers = list(target_stocks.keys())
    for i, t in enumerate(tickers):
        status_text.text(f"📊 分析中: {target_stocks[t]} ({i+1}/{len(tickers)})")
        try:
            df = yf.download(t, period="6mo", interval="1d", progress=False)
            if df.empty: continue
            
            # Seriesの抽出 (yfinanceのマルチインデックス対策)
            c = df['Close'].iloc[:,0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
            v = df['Volume'].iloc[:,0] if isinstance(df['Volume'], pd.DataFrame) else df['Volume']
            
            current_price = float(c.iloc[-1])
            avg_vol = v.tail(5).mean()
            
            # 条件フィルタ (株価条件 + 出来高条件)
            if current_price >= price_min and avg_vol >= vol_min:
                rsi = calculate_rsi(c, 14).iloc[-1]
                rci = calculate_rci(c, 9).iloc[-1]
                last_dc = get_dead_cross_info(df)
                
                # 緊急通知判定 (RCI 95以上 or RSI 90以上)
                if rci >= 95 or rsi >= 90:
                    requests.post(DISCORD_URL, json={"content": f"⚠️ **【Jack株AI：超過熱警告】**\n銘柄: {target_stocks[t]} ({t})\nRSI: {rsi:.1f} / RCI: {rci:.1f}\n天井圏到達の可能性。利益確定を検討してください。"})

                # AI詳細分析
                ai_data = get_ai_insight(t, target_stocks[t], current_price, rsi, rci)
                
                hits[t] = {
                    "name": target_stocks[t],
                    "price": current_price,
                    "rsi": round(rsi, 1),
                    "rci": round(rci, 1),
                    "vol": f"{avg_vol/10000:,.0f}万株",
                    "dead_cross": last_dc,
                    "driver": ai_data['driver'],
                    "trend": ai_data['trend_direction'],
                    "forecast_date": ai_data['forecast_date'],
                    "forecast_price": ai_data['forecast_price'],
                    "advice": ai_data['comment']
                }
        except Exception as e:
            print(f"Error scanning {t}: {e}")
        
        progress_bar.progress((i + 1) / len(tickers))
        time.sleep(1) # API制限回避

    # 結果保存
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": datetime.now().strftime('%Y-%m-%d %H:%M'), "hits": hits}, f, ensure_ascii=False, indent=2)
    
    st.balloons()
    return hits

# --- 🖥️ 画面レイアウト ---
st.title("🏆 Jack株AI：最終兵器ダッシュボード")
st.markdown("### AIによる市場連動要因分析 ＆ 上昇予報システム")

# サイドバー
st.sidebar.header("🔍 スキャン条件")
price_limit = st.sidebar.number_input("株価下限 (円)", value=3000, step=500)
vol_limit = st.sidebar.number_input("5日平均出来高下限 (株)", value=500000, step=100000)

if st.sidebar.button("🚀 AIフルスキャン ＆ 予報を開始", use_container_width=True):
    run_ultimate_scan(price_limit, vol_limit)

# メインエリア
if os.path.exists(PRE_SCAN_FILE):
    with open(PRE_SCAN_FILE, 'r', encoding='utf-8') as f:
        scan_data = json.load(f)
    
    st.subheader(f"✨ 条件合致銘柄 ＆ AI診断結果 ({scan_data['date']})")
    hits = scan_data.get('hits', {})
    
    if not hits:
        st.warning("現在、設定条件に合う有力銘柄は見つかりませんでした。条件を緩めて再試行してください。")
    else:
        # 銘柄カードの表示
        for t, info in hits.items():
            with st.expander(f"💎 **{info['name']}** ({t}) - 株価: {info['price']:,.0f}円", expanded=True):
                c1, c2, c3 = st.columns([1, 1.2, 1])
                
                with c1:
                    st.markdown("##### 📈 テクニカル")
                    st.write(f"**RSI:** {info['rsi']}")
                    st.write(f"**RCI:** {info['rci']}")
                    st.write(f"**最新DC日:** {info['dead_cross']}")
                    st.write(f"**平均出来高:** {info['vol']}")
                
                with c2:
                    st.markdown("##### 🌐 変動要因 ＆ トレンド")
                    st.info(f"**連動要因:**\n{info['driver']}")
                    st.write(f"**現在のトレンド:** {info['trend']}")
                    st.write(f"**AI助言:** {info['advice']}")
                
                with c3:
                    st.markdown("##### 🔮 AI上昇予報")
                    st.success(f"**上昇予想日:**\n{info['forecast_date']}")
                    st.metric("予想目標価格", f"{info['forecast_price']:,.0f}円", 
                              delta=f"{info['forecast_price'] - info['price']:,.1f}円")
                    
                if st.button(f"この銘柄を監視リストに保存 ({t})", key=f"save_{t}"):
                    # 監視リストへの追加ロジック
                    if os.path.exists(WATCHLIST_FILE):
                        with open(WATCHLIST_FILE, 'r') as f: wl = json.load(f)
                    else: wl = []
                    if t not in [x['ticker'] for x in wl]:
                        wl.append({"ticker": t, "name": info['name']})
                        with open(WATCHLIST_FILE, 'w') as f: json.dump(wl, f, ensure_ascii=False)
                        st.toast(f"{info['name']}を監視リストに入れました")

st.divider()

# リアルタイム監視リスト表示
if os.path.exists(WATCHLIST_FILE):
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    if watchlist:
        st.subheader("📋 監視リスト（ザラ場リアルタイム状況）")
        # 簡易テーブル表示ロジック
        wl_data = []
        for item in watchlist:
            try:
                d = yf.download(item['ticker'], period="1d", interval="1m", progress=False)
                last_p = d['Close'].iloc[-1,0] if isinstance(d['Close'], pd.DataFrame) else d['Close'].iloc[-1]
                wl_data.append({"銘柄": item['name'], "コード": item['ticker'], "現在価格": f"{last_p:,.1f}"})
            except: pass
        st.table(pd.DataFrame(wl_data))
