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

def get_rsi_vectorized(df, period):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss)))

# 💡 ユーザーの指摘に基づきRCIの符号を標準（チャート一致）に修正
def get_rci_vectorized(df, period):
    def rci_func(x):
        n = len(x)
        time_rank = np.arange(1, n + 1)
        price_rank = x.argsort().argsort() + 1
        d_sq = np.sum((time_rank - price_rank)**2)
        # 💡 標準的な計算に戻しました（チャートと一致します）
        return (1 - (6 * d_sq) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(rci_func)

def main():
    start_time = time.time()
    print("🚀 ジャック株AI：3系統スキャン（RCI修正版）開始...")
    
    TICKERS_DICT = get_prime_tickers()
    tickers_list = list(TICKERS_DICT.keys())
    
    # 📡 データ取得
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

    # ⚙️ 指標計算（短期・長期）
    rsi_s, rsi_l = get_rsi_vectorized(close_df, 9), get_rsi_vectorized(close_df, 14)
    rci_s, rci_l = get_rci_vectorized(close_df, 9), get_rci_vectorized(close_df, 26)
    ma20, ma60, ma200 = close_df.rolling(20).mean(), close_df.rolling(60).mean(), close_df.rolling(200).mean()
    vol_ma5 = volume_df.rolling(5).mean()

    # 通知用カテゴリ
    cond2_list = [] # 条件2: トレンド複合 (MA合致)
    cond1_groups = { # 条件1: 同時クロス項目別
        "✨同時GC": [], "💀同時DC": [], "🚀RSI10以下": [], "🔥大底": [], "⚠️急落": []
    }
    cond3_list = [] # 条件3: 数値クリアのみ (クロスなし)

    for symbol in close_df.columns:
        try:
            if vol_ma5[symbol].iloc[-1] < MIN_VOLUME_MA5: continue
            
            # 指標取得
            c_rs, c_rl, p_rs, p_rl = rsi_s[symbol].iloc[-1], rsi_l[symbol].iloc[-1], rsi_s[symbol].iloc[-2], rsi_l[symbol].iloc[-2]
            c_rcs, c_rcl, p_rcs, p_rcl = rci_s[symbol].iloc[-1], rci_l[symbol].iloc[-1], rci_s[symbol].iloc[-2], rci_l[symbol].iloc[-2]
            
            # MAトレンド判定
            m20, m60, m200 = ma20[symbol], ma60[symbol], ma200[symbol]
            is_up = (m20.iloc[-1] > m20.iloc[-2]) and (m60.iloc[-1] > m60.iloc[-2]) and (m200.iloc[-1] > m200.iloc[-2])
            is_down = (m20.iloc[-1] < m20.iloc[-2]) and (m60.iloc[-1] < m60.iloc[-2]) and (m200.iloc[-1] < m200.iloc[-2])
            
            # クロス判定
            rsi_gc, rci_gc = (p_rs <= p_rl and c_rs > c_rl), (p_rcs <= p_rcl and c_rcs > c_rcl)
            rsi_dc, rci_dc = (p_rs >= p_rl and c_rs < c_rl), (p_rcs >= p_rcl and c_rcs < c_rcl)

            # 数値判定
            num_buy = (c_rs <= 25 and c_rcs <= -70)
            num_sell = (c_rs >= 90 and c_rcs >= 95)
            sim_gc = (rsi_gc and rci_gc)
            sim_dc = (rsi_dc and rci_dc)

            price = f"{close_df[symbol].iloc[-1]:,.1f}"
            name = TICKERS_DICT.get(symbol, symbol)
            info = f"  ・{name} ({symbol}): RSI{c_rs:.1f}/RCI{c_rcs:.1f} [{price}円]"
            
            # 🏆 条件2: トレンド複合選定 (MA合致)
            if (is_up and (num_buy or sim_gc)) or (is_down and (num_sell or sim_dc)):
                cond2_list.append(f"{'📈上昇' if is_up else '📉下降'}: {info}")

            # 🔍 条件1: シグナル項目別 (同時クロス優先)
            if sim_gc: cond1_groups["✨同時GC"].append(info)
            elif sim_dc: cond1_groups["💀同時DC"].append(info)
            
            if c_rs <= 10: cond1_groups["🚀RSI10以下"].append(info)
            if c_rcs <= -95 and c_rs <= 20: cond1_groups["🔥大底"].append(info)
            elif c_rcs >= 95 and c_rs >= 80: cond1_groups["⚠️急落"].append(info)

            # 📝 条件3: 数値基準クリア (同時クロスがない銘柄をすべて)
            if (num_buy or num_sell) and not (sim_gc or sim_dc):
                prefix = "🟢買推奨" if num_buy else "🔴売推奨"
                cond3_list.append(f"{prefix}: {info}")

        except: continue

    # 📢 Discord通知構築
    now = datetime.now().strftime('%m/%d %H:%M')
    msg = f"📊 **【Jack株AI：3系統スキャン速報】** ({now})\n"
    msg += f"※RCI修正済み：チャートの数値と一致します\n\n"
    
    msg += "━━━ 🏆 条件2: トレンド複合選定 (MA合致) ━━━\n"
    msg += "\n".join(cond2_list) if cond2_list else "（現在、合致なし）"
    msg += "\n\n"
    
    msg += "━━━ 🔍 条件1: 同時クロス ＆ 特定シグナル ━━━\n"
    has_c1 = False
    for g, s in cond1_groups.items():
        if s:
            has_c1 = True
            msg += f"**{g}**\n" + "\n".join(s) + "\n"
    if not has_c1: msg += "（現在、シグナルなし）\n"
    
    msg += "\n━━━ 📝 条件3: 数値基準クリア (クロスなし) ━━━\n"
    msg += "\n".join(cond3_list) if cond3_list else "（現在、合致なし）"

    for i in range(0, len(msg), 1900):
        DiscordWebhook(url=DISCORD_URL, content=msg[i:i+1900]).execute()
        time.sleep(1)

    # 🤖 AI攻略本
    if cond2_list or cond3_list:
        prompt = f"日本株プロとして分析。特に条件2を本命、条件3を先回りとして評価し、目標株価と期待日を3行で簡潔に分析せよ。\n\n{msg}"
        try:
            api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            res = requests.post(api_url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]})
            if res.status_code == 200:
                ai_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                DiscordWebhook(url=DISCORD_URL, content=f"🤖 **【AI攻略本 (最新条件版)】**\n\n{ai_text}").execute()
        except: pass

    print(f"✅ スキャン完了！ 処理時間: {time.time() - start_time:.1f}秒")

if __name__ == "__main__":
    main()
