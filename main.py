import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from io import BytesIO

# --- 1. アプリ基本設定 ---
st.set_page_config(layout="wide", page_title="Jack株AI: Sakata Sniper", page_icon="🏹")

# --- 2. 銘柄名取得 ---
@st.cache_data(ttl=86400)
def get_jpx_names():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        df = pd.read_excel(BytesIO(res.content), engine='xlrd')
        return dict(zip(df['コード'].astype(str), df['銘柄名']))
    except: return {}
jpx_names = get_jpx_names()

# --- 3. 計算ロジック ---
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
    h, l, o, c = df['High'], df['Low'], df['Open'], df['Close']
    if (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-2] > o.iloc[-2]) and (c.iloc[-3] > o.iloc[-3]) and (c.iloc[-1] > c.iloc[-2]): return "🔆赤三兵"
    if (c.iloc[-2] < o.iloc[-2]) and (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-1] >= o.iloc[-2]): return "🔥陽の包み足"
    if l.iloc[-1] > h.iloc[-2]: return "✨上放れ窓"
    if (c.iloc[-3] < o.iloc[-3]) and (abs(c.iloc[-2] - o.iloc[-2]) < abs(c.iloc[-3] - o.iloc[-3]) * 0.2) and (c.iloc[-1] > o.iloc[-1]): return "🌅明けの明星"
    return "なし"

# --- 4. 診断エンジン ---
def diagnose_stock(code):
    try:
        df = yf.download(f"{code}.T", period="1y", interval="1d", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna().astype(float)
        
        df['RCI9'] = calculate_rci(df['Close'], 9)
        df['RCI27'] = calculate_rci(df['Close'], 27)
        df['Psy'] = calculate_psychological(df['Close'], 12)
        df['VWAP'] = calculate_vwap(df, 25)
        
        cur, pre = df.iloc[-1], df.iloc[-2]
        sakata = get_sakata_label(df)
        p = cur['Close']
        
        # 簡易判定
        rci_gc = (pre['RCI9'] < pre['RCI27'] and cur['RCI9'] >= cur['RCI27'])
        status, color = ("🚀 狙撃対象", "cyan") if (rci_gc or sakata != "なし") else ("☁️ 静観", "gray")
        
        return {"name": jpx_names.get(code, "銘柄"), "code": code, "price": int(p), "status": status, "color": color, "df": df, "checks": {"酒田五法": sakata, "RCIクロス": rci_gc, "Psy": f"{cur['Psy']:.0f}%", "VWAP乖離": f"{((p-cur['VWAP'])/cur['VWAP']*100):.1f}%"}}
    except: return None

# --- 5. UI構築 ---
st.title("🏹 Jack株AI: Sniper Precision Dashboard")
codes_input = st.text_area("Discordの銘柄コードを貼り付け", "")

if st.button("🩺 精密分析を実行", type="primary"):
    code_list = [x.strip() for x in codes_input.split(',') if x.strip()]
    for c in code_list:
        res = diagnose_stock(c)
        if res:
            st.markdown(f"### {res['name']} ({res['code']}) : {res['price']:,}円 [{res['status']}]")
            col_l, col_r = st.columns([1, 2])
            with col_l:
                for k, v in res['checks'].items(): st.write(f"**{k}**: {v}")
            with col_r:
                d_df = res['df'].tail(20) # 20日ズーム
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.03)
                fig.add_trace(go.Candlestick(x=d_df.index, open=d_df['Open'], high=d_df['High'], low=d_df['Low'], close=d_df['Close'], name='足'), row=1, col=1)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['VWAP'], line=dict(color='orange', width=2, dash='dot'), name='VWAP'), row=1, col=1)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['RCI9'], line=dict(color='red'), name='RCI9'), row=2, col=1)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['RCI27'], line=dict(color='navy'), name='RCI27'), row=2, col=1)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['Psy'], line=dict(color='green'), name='Psy'), row=3, col=1)
                fig.update_layout(height=700, xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,t=0,b=0))
                st.plotly_chart(fig, use_container_width=True)
            st.divider()
