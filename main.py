import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from io import BytesIO

# --- 1. アプリ基本設定 ---
st.set_page_config(layout="wide", page_title="Jack株AI: Sakata Sniper", page_icon="🏹")

# --- 2. 銘柄名取得（JPX） ---
@st.cache_data(ttl=86400)
def get_jpx_names():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        df = pd.read_excel(BytesIO(res.content), engine='xlrd')
        return dict(zip(df['コード'].astype(str), df['銘柄名']))
    except: return {}
jpx_names = get_jpx_names()

# --- 3. 指標計算ロジック ---
def calculate_rci(series, period):
    def rci_logic(s):
        n = len(s); tr = list(range(n, 0, -1)); pr = pd.Series(s).rank(ascending=False).tolist()
        return (1 - (6 * sum((t - p) ** 2 for t, p in zip(tr, pr))) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_logic)

def calculate_psychological(series, period=12):
    return ((series.diff() > 0).astype(int).rolling(window=period).sum() / period) * 100

def calculate_vwap(df, period=25):
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * df['Volume']).rolling(window=period).sum() / (df['Volume'].rolling(window=period).sum() + 1e-9)

def get_sakata_label(df):
    """酒田五法サイン判定"""
    h, l, o, c = df['High'], df['Low'], df['Open'], df['Close']
    if (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-2] > o.iloc[-2]) and (c.iloc[-3] > o.iloc[-3]) and (c.iloc[-1] > c.iloc[-2]): return "🔆赤三兵"
    if (c.iloc[-2] < o.iloc[-2]) and (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-1] >= o.iloc[-2]): return "🔥陽の包み足"
    if l.iloc[-1] > h.iloc[-2]: return "✨上放れ窓"
    return "なし"

# --- 4. 診断エンジン ---
def diagnose_stock(code, min_v):
    try:
        # 直近1年分のデータを取得（計算用）
        df = yf.download(f"{code}.T", period="1y", interval="1d", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna().astype(float)
        
        # 指標計算
        df['RCI9'] = calculate_rci(df['Close'], 9)
        df['RCI27'] = calculate_rci(df['Close'], 27)
        df['Psy'] = calculate_psychological(df['Close'], 12)
        df['VWAP'] = calculate_vwap(df, 25)
        df['std'] = df['Close'].rolling(20).std()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['BBU'] = df['MA20'] + 3 * df['std']
        
        cur, pre = df.iloc[-1], df.iloc[-2]
        sakata = get_sakata_label(df)
        p = cur['Close']
        
        # 判定ロジック
        rci_gc = (pre['RCI9'] < pre['RCI27'] and cur['RCI9'] >= cur['RCI27'])
        above_vwap = p > cur['VWAP']
        bb_limit = p >= cur['BBU'] * 0.98
        
        if (rci_gc or sakata != "なし") and above_vwap and not bb_limit:
            status, color = "🚀 狙撃対象 (High Potential)", "cyan"
        elif bb_limit:
            status, color = "🛑 下落警戒 (Overbought)", "red"
        else: status, color = "☁️ 静観 (Wait)", "gray"
        
        checks = {
            "酒田五法": sakata,
            "RCIクロス(9>27)": rci_gc,
            "VWAP(25日)突破": above_vwap,
            "サイコロジカル": f"{cur['Psy']:.0f}%",
            "過熱感(BB+3σ)": "到達" if bb_limit else "なし"
        }
        return {"name": jpx_names.get(code, "銘柄"), "code": code, "price": int(p), "status": status, "color": color, "df": df, "checks": checks}
    except: return None

# --- 5. 画面構築 ---
st.title("🏹 Jack株AI: Sakata Sniper Precision")
st.sidebar.markdown("### ⚙️ 精密設定")
min_v = st.sidebar.number_input("最低出来高", 0, 1000000, 300000)

codes_input = st.text_area("診断コード (例: 9984, 8035, 6834)", "9984, 8035")
if st.button("🩺 スナイパー診断 開始", type="primary"):
    code_list = [x.strip() for x in codes_input.split(',') if x.strip()]
    hit_codes = []
    
    for c in code_list:
        res = diagnose_stock(c, min_v)
        if res:
            hit_codes.append(res['code'])
            # 直近20日にズーム
            d_df = res['df'].tail(20)
            
            st.markdown(f"### {res['name']} ({res['code']}) : {res['price']:,}円")
            st.markdown(f"<h3 style='color:{res['color']}; background-color: rgba(0,0,0,0.1); padding: 10px; border-radius: 5px;'>判定: {res['status']}</h3>", unsafe_allow_html=True)
            
            col_l, col_r = st.columns([1, 2])
            with col_l:
                st.markdown("##### 📋 戦略合致チェック")
                for k, v in res['checks'].items(): st.write(f"**{k}**: {v}")
            with col_r:
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.03)
                # 1段目: ローソク & VWAP
                fig.add_trace(go.Candlestick(x=d_df.index, open=d_df['Open'], high=d_df['High'], low=d_df['Low'], close=d_df['Close'], name='価格'), row=1, col=1)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['VWAP'], line=dict(color='orange', width=2, dash='dot'), name='VWAP'), row=1, col=1)
                # 2段目: RCI (短期9 vs 長期27)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['RCI9'], line=dict(color='red', width=2), name='RCI9'), row=2, col=1)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['RCI27'], line=dict(color='navy', width=2), name='RCI27'), row=2, col=1)
                fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
                # 3段目: サイコロジカル
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['Psy'], line=dict(color='green', width=2), name='Psy'), row=3, col=1)
                fig.add_hline(y=50, line_dash="dot", line_color="rgba(128,128,128,0.5)", row=3, col=1)
                
                fig.update_layout(height=800, xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,t=0,b=0))
                st.plotly_chart(fig, use_container_width=True)
            st.divider()
    
    if hit_codes:
        st.subheader("📋 診断銘柄コピペ用リスト")
        st.code(",".join(hit_codes), language="text")
