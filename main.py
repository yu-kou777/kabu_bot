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
    print("📡 JPXからプライム銘柄リストを自動取得中...")
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        df_jpx = pd.read_excel(url)
        prime_df = df_jpx[df_jpx['市場・商品区分'] == 'プライム（内国株式）']
        tickers = {str(row['コード']) + ".T": row['銘柄名'] for _, row in prime_df.iterrows()}
        print(f"✅ プライム市場 {len(tickers)} 銘柄を取得しました。")
        return tickers
    except Exception as e:
        print(f"❌ リスト取得失敗: {e}")
        return {"8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG"}

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_rci(series, period=9):
    if len(series) < period: return np.zeros(len(series))
    rci = np.zeros(len(series))
    for i in range(period - 1, len(series)):
        data = series.iloc[i - period + 1 : i + 1]
        time_rank = np.arange(period, 0, -1)
        price_rank = data.rank(ascending=False).values
        diff_sq_sum = np.sum((time_rank - price_rank) ** 2)
        rci[i] = (1 - (6 * diff_sq_sum) / (period * (period**2 - 1))) * 100
    return rci

def main():
    print("🚀 ジャック株AI：プライム市場全体トレンドスキャン開始...")
    
    TICKERS = get_prime_tickers()
    tickers_list = list(TICKERS.keys())
    
    print("📡 株価・出来高データを取得中 (MA200計算のため2年分取得)...")
    close_prices_list = []
    volumes_list = []
    chunk_size = 150 # 安定のため少し絞る
    
    for i in range(0, len(tickers_list), chunk_size):
        chunk = tickers_list[i:i+chunk_size]
        # 💡 MA200のために2年分(2y)取得
        data = yf.download(chunk, period="2y", threads=True, progress=False)
        
        if not data.empty:
            if isinstance(data.columns, pd.MultiIndex):
                close_prices_list.append(data['Close'])
                volumes_list.append(data['Volume'])
            else:
                ticker = chunk[0]
                close_prices_list.append(data[['Close']].rename(columns={'Close': ticker}))
                volumes_list.append(data[['Volume']].rename(columns={'Volume': ticker}))
        time.sleep(2)
        
    if close_prices_list:
        close_prices = pd.concat(close_prices_list, axis=1)
        volumes = pd.concat(volumes_list, axis=1)
    else:
        print("❌ データの取得に失敗しました。")
        return

    # シグナルグループ用辞書（内部にMAトレンド別リストを保持）
    signal_groups = {
        "🔥【大底急騰期待】RCI最低値圏(-95以下) ＆ RSI20以下": {"up": [], "down": [], "mixed": []},
        "⚠️【急落警戒】RCI最高値圏(95以上) ＆ RSI80以上": {"up": [], "down": [], "mixed": []},
        "🟢【買い推奨】RSI25以下 ＆ RCI-70以下": {"up": [], "down": [], "mixed": []},
        "🔴【空売り推奨】RSI90以上 ＆ RCI95以上": {"up": [], "down": [], "mixed": []},
        "🚀【急騰期待】RSI10以下": {"up": [], "down": [], "mixed": []},
        "⤴️【反転シグナル】RSI・RCI同時に売られすぎ圏から上向き": {"up": [], "down": [], "mixed": []}
    }
    
    print("⚙️ 指標計算とMAトレンド判別中...")
    for symbol, name in TICKERS.items():
        try:
            if symbol not in close_prices.columns or symbol not in volumes.columns: continue
            
            series_close = close_prices[symbol].dropna()
            series_vol = volumes[symbol].dropna()
            
            if len(series_close) < 201 or len(series_vol) < 5: continue
            
            # 出来高フィルター
            vol_ma5 = series_vol.tail(5).mean()
            if vol_ma5 < MIN_VOLUME_MA5: continue
            
            # RSI/RCI計算
            rsi = round(calculate_rsi(series_close, 14).iloc[-1], 1)
            rci = round(calculate_rci(series_close, 9)[-1], 1)
            prev_rsi = round(calculate_rsi(series_close, 14).iloc[-2], 1)
            prev_rci = round(calculate_rci(series_close, 9)[-2], 1)
            
            # 💡 移動平均線(MA)計算とトレンド判定
            ma20 = series_close.rolling(window=20).mean()
            ma60 = series_close.rolling(window=60).mean()
            ma200 = series_close.rolling(window=200).mean()
            
            # 当日と前日の傾きチェック
            is_up = (ma20.iloc[-1] > ma20.iloc[-2]) and (ma60.iloc[-1] > ma60.iloc[-2]) and (ma200.iloc[-1] > ma200.iloc[-2])
            is_down = (ma20.iloc[-1] < ma20.iloc[-2]) and (ma60.iloc[-1] < ma60.iloc[-2]) and (ma200.iloc[-1] < ma200.iloc[-2])
            
            trend_key = "mixed"
            if is_up: trend_key = "up"
            elif is_down: trend_key = "down"
            
            price = f"{series_close.iloc[-1]:,.0f}"
            info_str = f"  ・{name} ({symbol}): RSI {rsi} / RCI {rci} [{price}円]"
            
            # 条件合致の振り分け
            target_group = None
            if rci <= -95 and rsi <= 20: target_group = "🔥【大底急騰期待】RCI最低値圏(-95以下) ＆ RSI20以下"
            elif rci >= 95 and rsi >= 80: target_group = "⚠️【急落警戒】RCI最高値圏(95以上) ＆ RSI80以上"
            elif rsi <= 25 and rci <= -70: target_group = "🟢【買い推奨】RSI25以下 ＆ RCI-70以下"
            elif rsi >= 90 and rci >= 95: target_group = "🔴【空売り推奨】RSI90以上 ＆ RCI95以上"
            elif rsi <= 10: target_group = "🚀【急騰期待】RSI10以下"
            elif (rci <= -50 and prev_rci < rci) and (rsi <= 30 and prev_rsi < rsi): target_group = "⤴️【反転シグナル】RSI・RCI同時に売られすぎ圏から上向き"
            
            if target_group:
                signal_groups[target_group][trend_key].append(info_str)
        except:
            pass

    # Discord用メッセージ構築
    now_str = datetime.now().strftime('%m/%d %H:%M')
    data_msg = f"📊 **【Jack株AI プライム・MAトレンド分析】** ({now_str})\n"
    data_msg += f"※MA判定：20/60/200日線がすべて上昇または下降\n\n"
    has_signals = False
    
    for sig_name, trends in signal_groups.items():
        if any(trends.values()):
            has_signals = True
            data_msg += f"**{sig_name}**\n"
            
            if trends["up"]:
                data_msg += " 📈 [全MA上昇中/強い上昇]\n" + "\n".join(trends["up"]) + "\n"
            if trends["down"]:
                data_msg += " 📉 [全MA下降中/強い下降]\n" + "\n".join(trends["down"]) + "\n"
            if trends["mixed"]:
                data_msg += " ➖ [MAトレンド混在]\n" + "\n".join(trends["mixed"]) + "\n"
            data_msg += "\n"
            
    if not has_signals:
        data_msg += "現在、シグナルに合致する銘柄はありません。\n"

    # Discord送信（分割）
    try:
        chunk_size = 1800
        chunks = [data_msg[i:i+chunk_size] for i in range(0, len(data_msg), chunk_size)]
        total = len(chunks)
        for idx, chunk in enumerate(chunks):
            header = f"【速報 ({idx+1}/{total})】\n" if total > 1 else ""
            DiscordWebhook(url=DISCORD_URL, content=header + chunk).execute()
            time.sleep(1)
        print("✅ 送信完了！")
    except Exception as e:
        print(f"❌ 送信失敗: {e}")

    # AI分析（シグナル銘柄のみ）
    if has_signals:
        prompt = f"日本株プロとして分析せよ。特に📈（全MA上昇）で逆張りシグナルが出ている銘柄を「底打ち成功」として高く評価し、銘柄ごとに3行で分析せよ。\n\n{data_msg}"
        try:
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            res = requests.post(url, headers={'Content-Type': 'application/json'}, json={"contents": [{"parts": [{"text": prompt}]}]})
            if res.status_code == 200:
                ai_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                DiscordWebhook(url=DISCORD_URL, content=f"🤖 **【AI攻略本 (トレンド選別)】**\n\n{ai_text}").execute()
        except:
            pass

if __name__ == "__main__":
    main()
