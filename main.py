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
MIN_VOLUME_MA5 = 300000 # 出来高フィルター：平均30万株以上

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
    print("🚀 ジャック株AI：条件1（標準）＆ 条件2（MA複合）同時スキャン開始...")
    
    TICKERS_DICT = get_prime_tickers()
    tickers_list = list(TICKERS_DICT.keys())
    
    # 📡 2年分のデータを分割取得（MA200計算用）
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

    # ⚙️ 指標一括計算（ベクトル演算で高速化）
    rsi_all = get_rsi_vectorized(close_df)
    rci_all = get_rci_vectorized(close_df)
    ma20_all = close_df.rolling(20).mean()
    ma60_all = close_df.rolling(60).mean()
    ma200_all = close_df.rolling(200).mean()
    vol_ma5_all = volume_df.rolling(5).mean()

    # 💡 カテゴリ分け（条件1と条件2）
    standard_reports = []  # 条件1: MA不問・数値クリアのみ
    compound_reports = []  # 条件2: MAトレンド合致（複合選定）

    for symbol in close_df.columns:
        try:
            # 出来高フィルター
            if vol_ma5_all[symbol].iloc[-1] < MIN_VOLUME_MA5: continue
            
            rsi, rci = rsi_all[symbol].iloc[-1], rci_all[symbol].iloc[-1]
            p_rsi, p_rci = rsi_all[symbol].iloc[-2], rci_all[symbol].iloc[-2]
            m20, m60, m200 = ma20_all[symbol], ma60_all[symbol], ma200_all[symbol]
            
            # MAトレンド判定
            is_all_up = (m20.iloc[-1] > m20.iloc[-2]) and (m60.iloc[-1] > m60.iloc[-2]) and (m200.iloc[-1] > m200.iloc[-2])
            is_all_down = (m20.iloc[-1] < m20.iloc[-2]) and (m60.iloc[-1] < m60.iloc[-2]) and (m200.iloc[-1] < m200.iloc[-2])
            
            price = f"{close_df[symbol].iloc[-1]:,.0f}"
            name = TICKERS_DICT.get(symbol, symbol)
            
            # --- 条件1: メモの数値条件判定 ---
            signal = None
            if rsi <= 25 and rci <= -70: signal = "🟢買い推奨"
            elif rsi >= 90 and rci >= 95: signal = "🔴空売り推奨"
            elif rci <= -95 and rsi <= 20: signal = "🔥大底期待"
            elif rci >= 95 and rsi >= 80: signal = "⚠️急落警戒"
            elif rsi <= 10: signal = "🚀超売られすぎ"
            elif (rci <= -50 and p_rci < rci) and (rsi <= 30 and p_rsi < rsi): signal = "⤴️反転シグナル"
            
            if signal:
                info = f"{signal} | {name} ({symbol}): RSI{rsi:.1f}/RCI{rci:.1f} [{price}円]"
                # 標準リストに追加
                standard_reports.append(info)
                
                # --- 条件2: MAトレンドとの複合判定 ---
                # 買い方向のシグナル ＋ 全MA上昇
                if is_all_up and ("買い" in signal or "大底" in signal or "反転" in signal or "すぎ" in signal):
                    compound_reports.append(f"📈上昇トレンド継続中: {info}")
                # 売り方向のシグナル ＋ 全MA下降
                elif is_all_down and ("空売り" in signal or "警戒" in signal):
                    compound_reports.append(f"📉下降トレンド継続中: {info}")
        except: continue

    # 📢 Discord用メッセージ構築
    now = datetime.now().strftime('%m/%d %H:%M')
    final_msg = f"📊 **【Jack株AI：ハイブリッド戦略速報】** ({now})\n\n"
    
    final_msg += "━━━ 🛠️ 条件2: MA複合選定 (トレンド一致) ━━━\n"
    final_msg += "\n".join(compound_reports) if compound_reports else "（合致銘柄なし）"
    final_msg += "\n\n"
    
    final_msg += "━━━ 🔍 条件1: 標準選定 (数値クリアのみ) ━━━\n"
    final_msg += "\n".join(standard_reports) if standard_reports else "（合致銘柄なし）"

    # Discord送信
    for i in range(0, len(final_msg), 1900):
        DiscordWebhook(url=DISCORD_URL, content=final_msg[i:i+1900]).execute()
        time.sleep(1)

    # AI分析
    if compound_reports or standard_reports:
        print("🤖 AI攻略本を執筆中...")
        prompt = f"日本株プロとして分析。特に条件2の『MAトレンド一致』銘柄を本命として評価し、目標株価と上昇期待日を銘柄ごとに3行で分析せよ。\n\n{final_msg}"
        try:
            api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            res = requests.post(api_url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]})
            if res.status_code == 200:
                ai_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                DiscordWebhook(url=DISCORD_URL, content=f"🤖 **【AI攻略本】**\n\n{ai_text}").execute()
        except: pass

    print(f"✅ スキャン完了！ 処理時間: {time.time() - start_time:.1f}秒")

if __name__ == "__main__":
    main()
