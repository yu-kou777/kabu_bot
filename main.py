import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import numpy as np
from io import BytesIO
from datetime import datetime
import pytz

# --- 1. アプリ基本設定 ---
st.set_page_config(layout="wide", page_title="Jack株AI: スイングプレシジョン", page_icon="🏹")

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

# --- 3. 計算ロジック（マスピ2・Discord通知側と完全同期） ---
def calculate_rci(series, period):
    def rci_logic(s):
        n = len(s); tr = list(range(n, 0, -1)); pr = pd.Series(s).rank(ascending=False).tolist()
        return (1 - (6 * sum((t - p) ** 2 for t, p in zip(tr, pr))) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_logic)

def calculate_psychological(series, period=12):
    return ((series.diff() > 0).astype(int).rolling(window=period).sum() / period) * 100

def calculate_dmi_custom(high_df, low_df, close_df, di_period=14, adx_period=9):
    """マスピ2設定：DI=14, ADX=9 に準拠したDMI計算"""
    up_move = high_df.diff()
    down_move = -low_df.diff()
    
    dm_pos = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    dm_neg = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    tr1 = high_df - low_df
    tr2 = (high_df - close_df.shift()).abs()
    tr3 = (low_df - close_df.shift()).abs()
    tr = pd.DataFrame(np.max([tr1, tr2, tr3], axis=0), index=close_df.index, columns=close_df.columns)
    
    atr = tr.rolling(window=di_period).mean()
    plus_di = (pd.DataFrame(dm_pos, index=close_df.index, columns=close_df.columns).rolling(window=di_period).mean() / (atr + 1e-9)) * 100
    minus_di = (pd.DataFrame(dm_neg, index=close_df.index, columns=close_df.columns).rolling(window=di_period).mean() / (atr + 1e-9)) * 100
    
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9) * 100
    adx = dx.rolling(window=adx_period).mean()
    
    return plus_di, minus_di, adx

# --- 4. 精密診断エンジン ---
def diagnose_stock(code):
    try:
        df = yf.download(f"{code}.T", period="1y", interval="1d", progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna().astype(float)
        
        # 指標計算
        df['RCI9'] = calculate_rci(df['Close'], 9)
        df['RCI27'] = calculate_rci(df['Close'], 27)
        df['Psy'] = calculate_psychological(df['Close'], 12)
        
        # DMI一括計算用のデータ成形
        p_di_df, m_di_df, adx_df = calculate_dmi_custom(
            pd.DataFrame({code: df['High']}), 
            pd.DataFrame({code: df['Low']}), 
            pd.DataFrame({code: df['Close']})
        )
        df['PlusDI'] = p_di_df[code]
        df['MinusDI'] = m_di_df[code]
        df['ADX'] = adx_df[code]
        
        cur, pre = df.iloc[-1], df.iloc[-2]
        p = cur['Close']
        
        # ーーー 📊 出来高データ算出 ーーー
        vol_3m_avg = df['Volume'].iloc[-60:].mean()
        vol_today = df['Volume'].iloc[-1]
        vol_ratio = vol_today / vol_3m_avg
        
        # ーーー 🎯 条件判定ロジック（Discord通知側と100%同期） ーーー
        is_rci_turn_up = (pre['RCI9'] <= -85 and cur['RCI9'] > pre['RCI9']) or (pre['RCI9'] <= -50 and cur['RCI9'] >= -50)
        is_psy_turn_up = (pre['Psy'] <= 25 and cur['Psy'] > pre['Psy']) or (cur['Psy'] >= 30 and pre['Psy'] <= 30)
        dmi_approaching = (cur['PlusDI'] > pre['PlusDI']) and (cur['MinusDI'] < pre['MinusDI']) and (cur['PlusDI'] < cur['MinusDI'])
        
        # 最終ステータス判定
        if (cur['RCI27'] >= -50) and is_rci_turn_up and is_psy_turn_up:
            status, color = "🔥 大底反転（即買い）", "red"
        elif (cur['RCI9'] <= -80) and (25 <= cur['Psy'] <= 35) and dmi_approaching:
            status, color = "📈 反転予兆（監視強化）", "blue"
        else:
            status, color = "☁️ 条件外（静観）", "gray"
            
        return {
            "name": jpx_names.get(code, "銘柄"), 
            "code": code, 
            "price": int(p), 
            "status": status, 
            "color": color, 
            "df": df, 
            "checks": {
                "ステータス": status,
                "本日出来高": f"{vol_ratio:.2f} 倍 (3ヶ月平均比)",
                "RCI短期(9)": f"{cur['RCI9']:.0f} (前日: {pre['RCI9']:.0f})",
                "RCI長期(27)": f"{cur['RCI27']:.0f}",
                "サイコロジカル": f"{cur['Psy']:.0f}%",
                "DMI状況": f"+DI:{cur['PlusDI']:.0f} / -DI:{cur['MinusDI']:.0f} (ADX:{cur['ADX']:.0f})"
            }
        }
    except Exception as e:
        return None

# --- 5. UI構築 ---
st.title("🏹 Jack株AI: Sniper Precision Dashboard")
st.markdown("Discordから届いた **コピペ用コード (番号のみ)** をそのまま貼り付けて精密分析を行えます。")

codes_input = st.text_area("銘柄コードを貼り付け（カンマ「,」や改行区切りに対応）", "6834, 9984", height=100)

if st.button("🩺 精密分析を実行", type="primary"):
    # スペース、改行、カンマを綺麗にパースしてコードリスト化
    raw_codes = codes_input.replace('\n', ',').split(',')
    code_list = [x.strip() for x in raw_codes if x.strip()]
    
    if not code_list:
        st.warning("銘柄コードを入力してください。")
    
    for c in code_list:
        res = diagnose_stock(c)
        if res:
            st.markdown(f"### {res['name']} ({res['code']}) : {res['price']:,}円 — `{res['status']}`")
            col_l, col_r = st.columns([1, 2])
            
            with col_l:
                st.markdown("#### 🔍 主要パラメータ分析")
                for k, v in res['checks'].items():
                    st.write(f"**{k}**: {v}")
            
            with col_r:
                d_df = res['df'].tail(40) # 動きが見えやすいよう40日表示に拡張
                
                # チャートの構成（4段構成：ローソク足、出来高、RCI、DMI/Psy）
                fig = make_subplots(
                    rows=4, cols=1, 
                    shared_xaxes=True, 
                    row_heights=[0.4, 0.15, 0.22, 0.23], 
                    vertical_spacing=0.03
                )
                
                # 1段目：ローソク足
                fig.add_trace(go.Candlestick(x=d_df.index, open=d_df['Open'], high=d_df['High'], low=d_df['Low'], close=d_df['Close'], name='足'), row=1, col=1)
                
                # 2段目：出来高
                fig.add_trace(go.Bar(x=d_df.index, y=d_df['Volume'], name='出来高', marker_color='gray'), row=2, col=1)
                
                # 3段目：RCI（短期=赤、長期=青）
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['RCI9'], line=dict(color='#ff3366', width=2), name='RCI9(短期)'), row=3, col=1)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['RCI27'], line=dict(color='#3399ff', width=2), name='RCI27(長期)'), row=3, col=1)
                fig.add_shape(type="line", x0=d_df.index[0], y0=-80, x1=d_df.index[-1], y1=-80, line=dict(color="gray", dash="dash"), row=3, col=1)
                fig.add_shape(type="line", x0=d_df.index[0], y0=-50, x1=d_df.index[-1], y1=-50, line=dict(color="lightgray", dash="dot"), row=3, col=1)
                
                # 4段目：DMI ＆ サイコロジカル
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['PlusDI'], line=dict(color='orange', width=1.5), name='+DI'), row=4, col=1)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['MinusDI'], line=dict(color='purple', width=1.5), name='-DI'), row=4, col=1)
                fig.add_trace(go.Scatter(x=d_df.index, y=d_df['Psy'], line=dict(color='green', width=2, dash='dot'), name='Psy(サイコロ)'), row=4, col=1)
                
                fig.update_layout(height=750, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
            st.divider()
        else:
            st.error(f"銘柄コード: {c} のデータ取得または分析に失敗しました。")
