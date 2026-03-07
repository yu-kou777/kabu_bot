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
    print("📡 JPXからプライム銘柄リストを取得中...")
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        df_jpx = pd.read_excel(url)
        prime_df = df_jpx[df_jpx['市場・商品区分'] == 'プライム（内国株式）']
        return {str(row['コード']) + ".T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except Exception as e:
        print(f"❌ リスト取得失敗: {e}")
        return {"8035.T": "東京エレクトロン"}

# 💡 RSIの高速ベクトル計算
def get_rsi_vectorized(df, period=14):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# 💡 RCIの超高速ベクトル計算
def get_rci_vectorized(df, period=9):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(n, 0, -1) - x.argsort().argsort() - 1)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_func)

def main():
    start_time = time.time()
    print("🚀 ジャック株AI：超高速スキャン開始...")
    
    TICKERS = get_prime_tickers()
    tickers_list = list(TICKERS.keys())
    
    # 1. 一括ダウンロード（期間を1.5年に短縮して軽量化）
    print(f"📡 {len(tickers_list)}銘柄のデータを並列取得中...")
    data = yf.download(tickers_list, period="1.5y", threads=True, progress=False)
    
    close_df = data['Close']
    volume_df = data['Volume']
    
    print("⚙️ 指標を一括計算中（ベクトル演算）...")
    # 全銘柄一括でテクニカル指標を計算
    rsi_all = get_rsi_vectorized(close_df)
    rci_all = get_rci_vectorized(close_df)
    ma20_all = close_df.rolling(20).mean()
    ma60_all = close_df.rolling(60).mean()
    ma200_all = close_df.rolling(200).mean()
    vol_ma5_all = volume_df.rolling(5).mean()

    # シグナルグループ
    signal_groups = {
        "🔥【大底急騰期待】RCI≦-95 ＆ RSI≦20": {"up": [], "down": [], "mixed": []},
        "⚠️【急落警戒】RCI≧95 ＆ RSI≧80": {"up": [], "down": [], "mixed": []},
        "🟢【買い推奨】RSI≦25 ＆ RCI≦-70": {"up": [], "down": [], "mixed": []},
        "🔴【空売り推奨】RSI≧90 ＆ RCI≧95": {"up": [], "down": [], "mixed": []},
        "🚀【急騰期待】RSI≦10": {"up": [], "down": [], "mixed": []},
        "⤴️【反転シグナル】売られすぎ圏から同時上向き": {"up": [], "down": [], "mixed": []}
    }
    
    print("🎯 シグナルを抽出中...")
    for symbol in tickers_list:
        try:
            if symbol not in rsi_all.columns: continue
            
            # 出来高フィルター
            if vol_ma5_all[symbol].iloc[-1] < MIN_VOLUME_MA5: continue
            
            # 各種数値の取得
            rsi, rci = rsi_all[symbol].iloc[-1], rci_all[symbol].iloc[-1]
            p_rsi, p_rci = rsi_all[symbol].iloc[-2], rci_all[symbol].iloc[-2]
            
            # MAトレンド判定
            m20, m60, m200 = ma20_all[symbol], ma60_all[symbol], ma200_all[symbol]
            is_up = (m20.iloc[-1] > m20.iloc[-2]) and (m60.iloc[-1] > m60.iloc[-2]) and (m200.iloc[-1] > m200.iloc[-2])
            is_down = (m20.iloc[-1] < m20.iloc[-2]) and (m60.iloc[-1] < m60.iloc[-2]) and (m200.iloc[-1] < m200.iloc[-2])
            trend_key = "up" if is_up else "down" if is_down else "mixed"
            
            price = f"{close_df[symbol].iloc[-1]:,.0f}"
            info = f"  ・{TICKERS[symbol]} ({symbol}): RSI{rsi:.1f}/RCI{rci:.1f} [{price}円]"
            
            # 判定（ジャックさんの厳選条件）
            target = None
            if rci <= -95 and rsi <= 20: target = "🔥【大底急騰期待】RCI≦-95 ＆ RSI≦20"
            elif rci >= 95 and rsi >= 80: target = "⚠️【急落警戒】RCI≧95 ＆ RSI≧80"
            elif rsi <= 25 and rci <= -70: target = "🟢【買い推奨】RSI≦25 ＆ RCI≦-70"
            elif rsi >= 90 and rci >= 95: target = "🔴【空売り推奨】RSI≧90 ＆ RCI≧95"
            elif rsi <= 10: target = "🚀【急騰期待】RSI≦10"
            elif (rci <= -50 and p_rci < rci) and (rsi <= 30 and p_rsi < rsi): target = "⤴️【反転シグナル】売られすぎ圏から同時上向き"
            
            if target: signal_groups[target][trend_key].append(info)
        except:
            pass

    # メッセージ構築とDiscord送信（中略：以前のロジックと同様）
    now_str = datetime.now().strftime('%m/%d %H:%M')
    data_msg = f"📊 **【Jack株AI 超高速スキャン】** ({now_str})\n\n"
    has_signals = False
    for sig_name, trends in signal_groups.items():
        if any(trends.values()):
            has_signals = True
            data_msg += f"**{sig_name}**\n"
            if trends["up"]: data_msg += " 📈 [全MA上昇]\n" + "\n".join(trends["up"]) + "\n"
            if trends["down"]: data_msg += " 📉 [全MA下降]\n" + "\n".join(trends["down"]) + "\n"
            if trends["mixed"]: data_msg += " ➖ [MA混在]\n" + "\n".join(trends["mixed"]) + "\n"
            data_msg += "\n"

    # 分割送信
    for i in range(0, len(data_msg), 1800):
        DiscordWebhook(url=DISCORD_URL, content=data_msg[i:i+1800]).execute()
        time.sleep(1)

    # AI分析
    if has_signals:
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        requests.post(url, json={"contents": [{"parts": [{"text": f"日本株プロとして分析せよ。特に📈の押し目買い候補を評価し、銘柄ごとに3行で分析せよ。\n\n{data_msg}"}]}]})

    print(f"✅ 完了！ 処理時間: {time.time() - start_time:.1f}秒")

if __name__ == "__main__":
    main()
