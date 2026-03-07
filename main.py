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
MIN_VOLUME_MA5 = 300000 # 5日平均出来高30万株以上

def get_prime_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        df_jpx = pd.read_excel(url)
        prime_df = df_jpx[df_jpx['市場・商品区分'] == 'プライム（内国株式）']
        return {str(row['コード']) + ".T": row['銘柄名'] for _, row in prime_df.iterrows()}
    except:
        return {"8035.T": "東京エレクトロン"}

def get_rsi_vectorized(df, period):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def get_rci_vectorized(df, period):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(n, 0, -1) - x.argsort().argsort() - 1)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_func)

def main():
    start_time = time.time()
    print("🚀 ジャック株AI：短期・長期クロス判定スキャン開始...")
    
    TICKERS_DICT = get_prime_tickers()
    tickers_list = list(TICKERS_DICT.keys())
    
    # 📡 2年分のデータを分割取得
    all_close, all_volume = [], []
    chunk_size = 300
    for i in range(0, len(tickers_list), chunk_size):
        chunk = tickers_list[i:i+chunk_size]
        data = yf.download(chunk, period="2y", threads=True, progress=False, group_by='column')
        if not data.empty:
            all_close.append(data['Close'])
            all_volume.append(data['Volume'])
        time.sleep(1)
        
    close_df = pd.concat(all_close, axis=1)
    volume_df = pd.concat(all_volume, axis=1)

    # ⚙️ 指標一括計算（短期・長期のペア）
    print("⚙️ RSI/RCIの短期・長期線を計算中...")
    rsi_s = get_rsi_vectorized(close_df, 9)
    rsi_l = get_rsi_vectorized(close_df, 14)
    rci_s = get_rci_vectorized(close_df, 9)
    rci_l = get_rci_vectorized(close_df, 26)
    
    ma20_all = close_df.rolling(20).mean()
    ma60_all = close_df.rolling(60).mean()
    ma200_all = close_df.rolling(200).mean()
    vol_ma5_all = volume_df.rolling(5).mean()

    standard_reports = []  # 条件1: MA不問・数値/クロス
    compound_reports = []  # 条件2: MAトレンド合致（複合）

    print("🎯 シグナル判定中...")
    for symbol in close_df.columns:
        try:
            if vol_ma5_all[symbol].iloc[-1] < MIN_VOLUME_MA5: continue
            
            # 各指標の当日・前日値
            cur_rs, cur_rl = rsi_s[symbol].iloc[-1], rsi_l[symbol].iloc[-1]
            pre_rs, pre_rl = rsi_s[symbol].iloc[-2], rsi_l[symbol].iloc[-2]
            cur_rcs, cur_rcl = rci_s[symbol].iloc[-1], rci_l[symbol].iloc[-1]
            pre_rcs, pre_rcl = rci_s[symbol].iloc[-2], rci_l[symbol].iloc[-2]
            
            m20, m60, m200 = ma20_all[symbol], ma60_all[symbol], ma200_all[symbol]
            is_all_up = (m20.iloc[-1] > m20.iloc[-2]) and (m60.iloc[-1] > m60.iloc[-2]) and (m200.iloc[-1] > m200.iloc[-2])
            is_all_down = (m20.iloc[-1] < m20.iloc[-2]) and (m60.iloc[-1] < m60.iloc[-2]) and (m200.iloc[-1] < m200.iloc[-2])
            
            # 💡 短期・長期の交差判定
            rsi_gc = (pre_rs <= pre_rl) and (cur_rs > cur_rl)
            rci_gc = (pre_rcs <= pre_rcl) and (cur_rcs > cur_rcl)
            rsi_dc = (pre_rs >= pre_rl) and (cur_rs < cur_rl)
            rci_dc = (pre_rcs >= pre_rcl) and (cur_rcs < cur_rcl)

            price = f"{close_df[symbol].iloc[-1]:,.0f}"
            name = TICKERS_DICT.get(symbol, symbol)
            
            signal = None
            # ジャックさんのメモ条件
            if rsi_gc and rci_gc: signal = "✨同時ゴールデンクロス"
            elif rsi_dc and rci_dc: signal = "💀同時デッドクロス"
            elif cur_rs <= 25 and cur_rcs <= -70: signal = "🟢買い推奨(数値)"
            elif cur_rs >= 90 and cur_rcs >= 95: signal = "🔴空売り推奨(数値)"
            
            if signal:
                info = f"{signal} | {name} ({symbol}): RSI(9/14){cur_rs:.1f} / RCI(9/26){cur_rcs:.1f} [{price}円]"
                standard_reports.append(info)
                
                # トレンド複合判定
                if is_all_up and ("ゴールデン" in signal or "買い" in signal):
                    compound_reports.append(f"📈上昇トレンド×買い: {info}")
                elif is_all_down and ("デッド" in signal or "空売り" in signal):
                    compound_reports.append(f"📉下降トレンド×売り: {info}")
        except: continue

    # Discord報告
    now = datetime.now().strftime('%m/%d %H:%M')
    final_msg = f"📊 **【Jack株AI：短期長期クロス ＆ 2系統速報】** ({now})\n\n"
    final_msg += "━━━ ① トレンド複合選定 (MA合致) ━━━\n"
    final_msg += "\n".join(compound_reports) if compound_reports else "（合致銘柄なし）"
    final_msg += "\n\n━━━ ② 標準シグナル選定 (MA不問) ━━━\n"
    final_msg += "\n".join(standard_reports) if standard_reports else "（シグナル銘柄なし）"

    for i in range(0, len(final_msg), 1900):
        DiscordWebhook(url=DISCORD_URL, content=final_msg[i:i+1900]).execute()
        time.sleep(1)

    # AI分析
    if standard_reports:
        print("🤖 AI攻略本を執筆中...")
        prompt = f"日本株プロとして分析。特に✨同時GCかつ📈上昇トレンドの銘柄を最強の買い候補、💀同時DCかつ📉下降トレンドを最強の売り候補として、3行で分析せよ。\n\n{final_msg}"
        try:
            api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            res = requests.post(api_url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]})
            if res.status_code == 200:
                ai_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                DiscordWebhook(url=DISCORD_URL, content=f"🤖 **【AI攻略本 (短期・長期クロス解析)】**\n\n{ai_text}").execute()
        except: pass

    print(f"✅ 全工程完了！ 処理時間: {time.time() - start_time:.1f}秒")

if __name__ == "__main__":
    main()
