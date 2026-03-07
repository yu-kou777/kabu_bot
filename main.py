import yfinance as yf
import pandas as pd
import requests
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime

# --- 設定 ---
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
    print("🚀 ジャック株AI：超高速＆高安定スキャン開始...")
    
    TICKERS_DICT = get_prime_tickers()
    tickers_list = list(TICKERS_DICT.keys())
    
    # 💡 Yahooの制限を回避しつつ高速化（300銘柄ずつ並列取得）
    print(f"📡 {len(tickers_list)}銘柄のデータを分割取得中...")
    all_close, all_volume = [], []
    chunk_size = 300
    for i in range(0, len(tickers_list), chunk_size):
        chunk = tickers_list[i:i+chunk_size]
        # Periodを正規の '2y' に修正
        data = yf.download(chunk, period="2y", threads=True, progress=False, group_by='column')
        if not data.empty:
            all_close.append(data['Close'])
            all_volume.append(data['Volume'])
        time.sleep(1) # サーバーへの配慮
        
    close_df = pd.concat(all_close, axis=1)
    volume_df = pd.concat(all_volume, axis=1)

    print("⚙️ 指標を一括計算中...")
    rsi_all = get_rsi_vectorized(close_df)
    rci_all = get_rci_vectorized(close_df)
    ma20_all = close_df.rolling(20).mean()
    ma60_all = close_df.rolling(60).mean()
    ma200_all = close_df.rolling(200).mean()
    vol_ma5_all = volume_df.rolling(5).mean()

    signal_groups = {
        "🔥【大底急騰期待】RCI≦-95 ＆ RSI≦20": {"up": [], "down": [], "mixed": []},
        "⚠️【急落警戒】RCI≧95 ＆ RSI≧80": {"up": [], "down": [], "mixed": []},
        "🟢【買い推奨】RSI≦25 ＆ RCI≦-70": {"up": [], "down": [], "mixed": []},
        "🔴【空売り推奨】RSI≧90 ＆ RCI≧95": {"up": [], "down": [], "mixed": []},
        "🚀【急騰期待】RSI≦10": {"up": [], "down": [], "mixed": []},
        "⤴️【反転シグナル】売られすぎ圏から同時上向き": {"up": [], "down": [], "mixed": []}
    }
    
    for symbol in close_df.columns:
        try:
            if vol_ma5_all[symbol].iloc[-1] < MIN_VOLUME_MA5: continue
            
            rsi, rci = rsi_all[symbol].iloc[-1], rci_all[symbol].iloc[-1]
            p_rsi, p_rci = rsi_all[symbol].iloc[-2], rci_all[symbol].iloc[-2]
            m20, m60, m200 = ma20_all[symbol], ma60_all[symbol], ma200_all[symbol]
            
            is_up = (m20.iloc[-1] > m20.iloc[-2]) and (m60.iloc[-1] > m60.iloc[-2]) and (m200.iloc[-1] > m200.iloc[-2])
            is_down = (m20.iloc[-1] < m20.iloc[-2]) and (m60.iloc[-1] < m60.iloc[-2]) and (m200.iloc[-1] < m200.iloc[-2])
            trend = "up" if is_up else "down" if is_down else "mixed"
            
            price = f"{close_df[symbol].iloc[-1]:,.0f}"
            info = f"  ・{TICKERS_DICT.get(symbol, symbol)} ({symbol}): RSI{rsi:.1f}/RCI{rci:.1f} [{price}円]"
            
            target = None
            if rci <= -95 and rsi <= 20: target = "🔥【大底急騰期待】RCI≦-95 ＆ RSI≦20"
            elif rci >= 95 and rsi >= 80: target = "⚠️【急落警戒】RCI≧95 ＆ RSI≧80"
            elif rsi <= 25 and rci <= -70: target = "🟢【買い推奨】RSI≦25 ＆ RCI≦-70"
            elif rsi >= 90 and rci >= 95: target = "🔴【空売り推奨】RSI≧90 ＆ RCI≧95"
            elif rsi <= 10: target = "🚀【急騰期待】RSI≦10"
            elif (rci <= -50 and p_rci < rci) and (rsi <= 30 and p_rsi < rsi): target = "⤴️【反転シグナル】売られすぎ圏から同時上向き"
            
            if target: signal_groups[target][trend].append(info)
        except: continue

    now = datetime.now().strftime('%m/%d %H:%M')
    msg = f"📊 **【Jack株AI 超高速・全市場スキャン】** ({now})\n\n"
    has_sig = False
    for group, trends in signal_groups.items():
        if any(trends.values()):
            has_sig = True
            msg += f"**{group}**\n"
            if trends['up']: msg += f" 📈 [全MA上昇]\n" + "\n".join(trends['up']) + "\n"
            if trends['down']: msg += f" 📉 [全MA下降]\n" + "\n".join(trends['down']) + "\n"
            if trends['mixed']: msg += f" ➖ [MA混在]\n" + "\n".join(trends['mixed']) + "\n"
            msg += "\n"

    # Discord送信
    for i in range(0, len(msg), 1800):
        DiscordWebhook(url=DISCORD_URL, content=msg[i:i+1800]).execute()
        time.sleep(1)

    if has_sig:
        # AI分析
        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        requests.post(api_url, json={"contents": [{"parts": [{"text": f"日本株プロとして分析せよ。特に📈の強い上昇トレンドでの押し目買い候補を評価し、銘柄ごとに3行で分析せよ。\n\n{msg}"}]}]})

    print(f"✅ 完了！ 処理時間: {time.time() - start_time:.1f}秒")

if __name__ == "__main__":
    main()

