import yfinance as yf
import pandas as pd
import requests
from discord_webhook import DiscordWebhook
import time
import numpy as np
from datetime import datetime
import pytz
import jpholiday

# --- 基本設定 ---
GEMINI_KEY = "AIzaSyCCnORqVcj51CzjvIX8-x2936m8iCbgQgA"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
MIN_VOLUME_MA5 = 300000 

def is_market_holiday():
    """市場が休み（土日・祝日）かどうかを判定する"""
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    # 土日判定
    if now.weekday() >= 5:
        return True
    # 日本の祝日判定
    if jpholiday.is_holiday(now.date()):
        return True
    return False

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
        time_rank = np.arange(1, n + 1)
        price_rank = pd.Series(x).rank().values
        d_sq = np.sum((time_rank - price_rank)**2)
        return (1 - (6 * d_sq) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_func)

def main():
    # 💡 冒頭で休日チェック
    if is_market_holiday():
        print("☕ 今日は日本市場が休み（土日・祝日）のため、スキャンを停止します。")
        return

    start_time = time.time()
    print("🚀 ジャック株AI：最新条件・休日判定スキャン開始...")
    
    TICKERS_DICT = get_prime_tickers()
    tickers_list = list(TICKERS_DICT.keys())
    
    print(f"📡 {len(tickers_list)}銘柄のデータを取得中...")
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

    rsi_s, rsi_l = get_rsi_vectorized(close_df, 9), get_rsi_vectorized(close_df, 14)
    rci_s, rci_l = get_rci_vectorized(close_df, 9), get_rci_vectorized(close_df, 26)
    ma20, ma60, ma200 = close_df.rolling(20).mean(), close_df.rolling(60).mean(), close_df.rolling(200).mean()
    vol_ma5 = volume_df.rolling(5).mean()

    cond2_list, cond3_list = [], []
    cond1_groups = {"✨同時GC": [], "💀同時DC": [], "🚀RSI10以下": [], "🔥大底": [], "⚠️急落": []}

    for symbol in close_df.columns:
        try:
            if vol_ma5[symbol].iloc[-1] < MIN_VOLUME_MA5: continue
            
            c_rs, c_rl, p_rs, p_rl = rsi_s[symbol].iloc[-1], rsi_l[symbol].iloc[-1], rsi_s[symbol].iloc[-2], rsi_l[symbol].iloc[-2]
            c_rcs, c_rcl, p_rcs, p_rcl = rci_s[symbol].iloc[-1], rci_l[symbol].iloc[-1], rci_s[symbol].iloc[-2], rci_l[symbol].iloc[-2]
            
            m20, m60, m200 = ma20[symbol].iloc[-1], ma60[symbol].iloc[-1], ma200[symbol].iloc[-1]
            p_m20, p_m60, p_m200 = ma20[symbol].iloc[-2], ma60[symbol].iloc[-2], ma200[symbol].iloc[-2]
            
            is_up = (m20 > p_m20) and (m60 > p_m60) and (m200 > p_m200)
            is_down = (m20 < p_m20) and (m60 < p_m60) and (m200 < p_m200)
            
            rsi_gc, rci_gc = (p_rs <= p_rl and c_rs > c_rl), (p_rcs <= p_rcl and c_rcs > c_rcl)
            rsi_dc, rci_dc = (p_rs >= p_rl and c_rs < c_rl), (p_rcs >= p_rcl and c_rcs < c_rcl)

            num_buy = (c_rs <= 20 and c_rcs <= -70)
            num_sell = (c_rs >= 90 and c_rcs >= 95)
            sim_gc, sim_dc = (rsi_gc and rci_gc), (rsi_dc and rci_dc)

            price = f"{close_df[symbol].iloc[-1]:,.1f}"
            name = TICKERS_DICT.get(symbol, symbol)
            info = f"  ・{name} ({symbol}): RSI{c_rs:.1f}/RCI{c_rcs:.1f} [{price}円]"
            
            if (is_up and (num_buy or sim_gc)) or (is_down and (num_sell or sim_dc)):
                cond2_list.append(f"{'📈上昇' if is_up else '📉下降'}: {info}")

            if sim_gc: cond1_groups["✨同時GC"].append(info)
            elif sim_dc: cond1_groups["💀同時DC"].append(info)
            if c_rs <= 10: cond1_groups["🚀RSI10以下"].append(info)
            if c_rcs <= -95 and c_rs <= 20: cond1_groups["🔥大底"].append(info)
            elif c_rcs >= 95 and c_rs >= 80: cond1_groups["⚠️急落"].append(info)

            if (num_buy or num_sell) and not (sim_gc or sim_dc):
                prefix = "🟢買推奨" if num_buy else "🔴売推奨"
                cond3_list.append(f"{prefix}: {info}")
        except: continue

    msg = f"📊 **【Jack株AI：3系統スキャン速報】** ({datetime.now(pytz.timezone('Asia/Tokyo')).strftime('%m/%d %H:%M')})\n"
    msg += f"※土日・祝日は自動でスキップされる設定です\n\n"
    
    msg += "━━━ 🏆 条件2: トレンド複合選定 ━━━\n" + ("\n".join(cond2_list) if cond2_list else "（合致なし）")
    msg += "\n\n━━━ 🔍 条件1: 同時クロス ＆ 特定シグナル ━━━\n"
    has_c1 = False
    for g, s in cond1_groups.items():
        if s:
            has_c1, msg = True, msg + f"**{g}**\n" + "\n".join(s) + "\n"
    if not has_c1: msg += "（シグナルなし）\n"
    
    msg += "\n━━━ 📝 条件3: 数値基準クリア (クロスなし) ━━━\n" + ("\n".join(cond3_list) if cond3_list else "（合致なし）")

    for i in range(0, len(msg), 1900):
        DiscordWebhook(url=DISCORD_URL, content=msg[i:i+1900]).execute()
        time.sleep(1)

    if cond2_list or cond3_list:
        prompt = f"日本株プロとして分析。条件2を本命、条件3を先回りとして評価し、目標株価と期待日を分析せよ。\n\n{msg}"
        try:
            api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            res = requests.post(api_url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]})
            if res.status_code == 200:
                ai_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                DiscordWebhook(url=DISCORD_URL, content=f"🤖 **【AI攻略本】**\n\n{ai_text}").execute()
        except: pass

if __name__ == "__main__":
    main()
