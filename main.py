import yfinance as yf
import pandas as pd
import requests
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime

# --- 基本設定 ---
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
MIN_VOLUME_MA5 = 300000

def get_prime_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        df_jpx = pd.read_excel(url)
        prime_df = df_jpx[df_jpx['市場・商品区分'] == 'プライム（内国株式）']
        return {str(row['コード']) + ".T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except:
        return {"8035.T": "東京エレクトロン"}

def get_rsi_vectorized(df, period=14):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def get_rci_vectorized(df, period=9):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(n, 0, -1) - x.argsort().argsort() - 1)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_func)

def main():
    start_time = time.time()
    print("🚀 ジャック株AI：2系統ハイブリッドスキャン開始...")
    
    TICKERS_DICT = get_prime_tickers()
    tickers_list = list(TICKERS_DICT.keys())
    
    # データ取得（MA200のために2年分）
    print(f"📡 {len(tickers_list)}銘柄のデータを分割取得中...")
    all_close, all_volume = [], []
    chunk_size = 400
    for i in range(0, len(tickers_list), chunk_size):
        chunk = tickers_list[i:i+chunk_size]
        data = yf.download(chunk, period="2y", threads=True, progress=False, group_by='column')
        if not data.empty:
            all_close.append(data['Close'])
            all_volume.append(data['Volume'])
        time.sleep(1)
        
    close_df = pd.concat(all_close, axis=1)
    volume_df = pd.concat(all_volume, axis=1)

    # テクニカル指標計算
    rsi_all = get_rsi_vectorized(close_df)
    rci_all = get_rci_vectorized(close_df)
    ma20_all = close_df.rolling(20).mean()
    ma60_all = close_df.rolling(60).mean()
    ma200_all = close_df.rolling(200).mean()
    vol_ma5_all = volume_df.rolling(5).mean()

    # 💡 2つの出力カテゴリを用意
    standard_reports = []  # MA無視（数値のみ）
    compound_reports = []  # MAトレンド合致（複合）

    for symbol in close_df.columns:
        try:
            if vol_ma5_all[symbol].iloc[-1] < MIN_VOLUME_MA5: continue
            
            rsi, rci = rsi_all[symbol].iloc[-1], rci_all[symbol].iloc[-1]
            p_rsi, p_rci = rsi_all[symbol].iloc[-2], rci_all[symbol].iloc[-2]
            m20, m60, m200 = ma20_all[symbol], ma60_all[symbol], ma200_all[symbol]
            
            # MAトレンド判定（パーフェクトオーダー）
            is_all_up = (m20.iloc[-1] > m20.iloc[-2]) and (m60.iloc[-1] > m60.iloc[-2]) and (m200.iloc[-1] > m200.iloc[-2])
            is_all_down = (m20.iloc[-1] < m20.iloc[-2]) and (m60.iloc[-1] < m60.iloc[-2]) and (m200.iloc[-1] < m200.iloc[-2])
            
            price = f"{close_df[symbol].iloc[-1]:,.0f}"
            name = TICKERS_DICT.get(symbol, symbol)
            
            # --- 判定ロジック（ジャックさん専用条件） ---
            signal_type = None
            if rci <= -95 and rsi <= 20: signal_type = "🔥大底期待"
            elif rci >= 95 and rsi >= 80: signal_type = "⚠️急落警戒"
            elif rsi <= 25 and rci <= -70: signal_type = "🟢買い推奨"
            elif rsi >= 90 and rci >= 95: signal_type = "🔴空売り推奨"
            elif rsi <= 10: signal_type = "🚀超売られすぎ"
            elif (rci <= -50 and p_rci < rci) and (rsi <= 30 and p_rsi < rsi): signal_type = "⤴️反転シグナル"
            
            if signal_type:
                info = f"{signal_type} | {name} ({symbol}): RSI{rsi:.1f}/RCI{rci:.1f} [{price}円]"
                # 1. まずは「標準」にすべて追加
                standard_reports.append(info)
                
                # 2. トレンドに合致していれば「複合」にも追加
                if (is_all_up and "買い" in signal_type) or (is_all_up and "大底" in signal_type) or (is_all_up and "反転" in signal_type):
                    compound_reports.append(f"📈上昇トレンド合致: {info}")
                elif (is_all_down and "空売り" in signal_type) or (is_all_down and "警戒" in signal_type):
                    compound_reports.append(f"📉下降トレンド合致: {info}")
        except: continue

    # メッセージ構築
    now = datetime.now().strftime('%m/%d %H:%M')
    final_msg = f"📊 **【Jack株AI：2系統抽出速報】** ({now})\n\n"
    
    final_msg += "━━━ ① トレンド複合選定 (MA合致) ━━━\n"
    final_msg += "\n".join(compound_reports) if compound_reports else "現在、合致銘柄なし"
    final_msg += "\n\n"
    
    final_msg += "━━━ ② 標準シグナル選定 (MA不問) ━━━\n"
    final_msg += "\n".join(standard_reports) if standard_reports else "現在、合致銘柄なし"

    # Discord送信
    for i in range(0, len(final_msg), 1900):
        DiscordWebhook(url=DISCORD_URL, content=final_msg[i:i+1900]).execute()
        time.sleep(1)

    print(f"✅ 完了！ 処理時間: {time.time() - start_time:.1f}秒")

if __name__ == "__main__":
    main()
