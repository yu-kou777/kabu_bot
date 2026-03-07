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
    print("🚀 ジャック株AI：プライム市場全体スキャン開始...")
    
    TICKERS = get_prime_tickers()
    tickers_list = list(TICKERS.keys())
    
    print("📡 株価データと出来高を分割ダウンロード中...")
    close_prices_list = []
    volumes_list = []
    chunk_size = 200
    
    for i in range(0, len(tickers_list), chunk_size):
        chunk = tickers_list[i:i+chunk_size]
        data = yf.download(chunk, period="6mo", threads=True, progress=False)
        
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

    # 💡 買い推奨の条件を厳格化（通知数を絞るため）
    groups = {
        "🔥【大底急騰期待】RCI最低値圏(-95以下) ＆ RSI20以下": [],
        "⚠️【急落警戒】RCI最高値圏(95以上) ＆ RSI80以上": [],
        "🟢【買い推奨】RSI25以下 ＆ RCI-70以下": [],
        "🔴【空売り推奨】RSI90以上 ＆ RCI95以上": [],
        "🚀【急騰期待】RSI10以下": [],
        "⤴️【反転シグナル】RSI・RCI同時に売られすぎ圏から上向き": []
    }
    
    print("⚙️ テクニカル指標と出来高フィルターを計算中...")
    for symbol, name in TICKERS.items():
        try:
            if symbol not in close_prices.columns or symbol not in volumes.columns: continue
            
            series_close = close_prices[symbol].dropna()
            series_vol = volumes[symbol].dropna()
            
            if len(series_close) < 15 or len(series_vol) < 5: continue
            
            vol_ma5 = series_vol.tail(5).mean()
            if vol_ma5 < MIN_VOLUME_MA5:
                continue
            
            rsi = round(calculate_rsi(series_close, 14).iloc[-1], 1)
            rci = round(calculate_rci(series_close, 9)[-1], 1)
            prev_rsi = round(calculate_rsi(series_close, 14).iloc[-2], 1)
            prev_rci = round(calculate_rci(series_close, 9)[-2], 1)
            price = f"{series_close.iloc[-1]:,.0f}"
            vol_str = f"{vol_ma5/10000:.0f}万株"
            
            info_str = f"  ・{name} ({symbol}): RSI {rsi} / RCI {rci} [{price}円 | 平均出来高 {vol_str}]"
            
            if rci <= -95 and rsi <= 20:
                groups["🔥【大底急騰期待】RCI最低値圏(-95以下) ＆ RSI20以下"].append(info_str)
            elif rci >= 95 and rsi >= 80:
                groups["⚠️【急落警戒】RCI最高値圏(95以上) ＆ RSI80以上"].append(info_str)
            # 💡 判定ロジックも RSI<=25 かつ RCI<=-70 に変更
            elif rsi <= 25 and rci <= -70:
                groups["🟢【買い推奨】RSI25以下 ＆ RCI-70以下"].append(info_str)
            elif rsi >= 90 and rci >= 95:
                groups["🔴【空売り推奨】RSI90以上 ＆ RCI95以上"].append(info_str)
            elif rsi <= 10:
                groups["🚀【急騰期待】RSI10以下"].append(info_str)
            elif (rci <= -50 and prev_rci < rci) and (rsi <= 30 and prev_rsi < rsi):
                groups["⤴️【反転シグナル】RSI・RCI同時に売られすぎ圏から上向き"].append(info_str)
        except:
            pass

    now_str = datetime.now().strftime('%m/%d %H:%M')
    data_msg = f"📊 **【Jack株AI プライム選抜 スキャン速報】** ({now_str})\n"
    data_msg += f"※流動性フィルター：5日平均出来高 {MIN_VOLUME_MA5/10000:.0f}万株以上\n\n"
    has_signals = False
    
    for group_name, stocks in groups.items():
        if stocks:
            has_signals = True
            data_msg += f"**{group_name}** ({len(stocks)}銘柄)\n"
            for stock in stocks:
                data_msg += f"{stock}\n"
            data_msg += "\n"
            
    if not has_signals:
        data_msg += "現在、指定の強力なシグナルと出来高条件に合致する銘柄はありません。\n"

    try:
        chunk_size = 1800
        chunks = [data_msg[i:i+chunk_size] for i in range(0, len(data_msg), chunk_size)]
        total_chunks = len(chunks)
        
        for idx, chunk in enumerate(chunks):
            header = ""
            if total_chunks > 1:
                header = f"【速報 ({idx+1}/{total_chunks})】\n"
            
            DiscordWebhook(url=DISCORD_URL, content=header + chunk).execute()
            time.sleep(1)
        print("✅ 第一陣：戦略シグナル速報の送信完了！")
    except Exception as e:
        print(f"❌ 速報の送信に失敗: {e}")

    if has_signals:
        print("🤖 AIがシグナル抽出銘柄の攻略本を執筆中...")
        prompt = f"日本株プロとしてテクニカル分析せよ。以下のシグナル点灯銘柄（出来高選抜済み）について、変動要因、上昇期待日、目標株価を銘柄ごとに3行で簡潔に分析せよ。\n\n{data_msg}"
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            headers = {'Content-Type': 'application/json'}
            data = {"contents": [{"parts": [{"text": prompt}]}]}
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                ai_analysis = response.json()['candidates'][0]['content']['parts'][0]['text']
                ai_msg = f"🤖 **【AI攻略本 (流動性厳選)】**\n\n{ai_analysis}"
                
                ai_chunks = [ai_msg[i:i+chunk_size] for i in range(0, len(ai_msg), chunk_size)]
                ai_total = len(ai_chunks)
                
                for idx, chunk in enumerate(ai_chunks):
                    header = ""
                    if ai_total > 1:
                        header = f"【AI攻略本 ({idx+1}/{ai_total})】\n"
                    DiscordWebhook(url=DISCORD_URL, content=header + chunk).execute()
                    time.sleep(1)
                print("✅ 第二陣：AI攻略本の送信完了！")
            else:
                # 💡 404エラーが出た場合のバックアップ（旧型・安定モデルに切り替え）
                print(f"⚠️ gemini-1.5-flash でエラー (コード: {response.status_code})。安定版(gemini-pro)で再試行します...")
                url_fallback = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_KEY}"
                response_fb = requests.post(url_fallback, headers=headers, json=data)
                
                if response_fb.status_code == 200:
                    ai_analysis = response_fb.json()['candidates'][0]['content']['parts'][0]['text']
                    ai_msg = f"🤖 **【AI攻略本 (安定版)】**\n\n{ai_analysis}"
                    
                    ai_chunks = [ai_msg[i:i+chunk_size] for i in range(0, len(ai_msg), chunk_size)]
                    ai_total = len(ai_chunks)
                    for idx, chunk in enumerate(ai_chunks):
                        header = ""
                        if ai_total > 1:
                            header = f"【AI攻略本 ({idx+1}/{ai_total})】\n"
                        DiscordWebhook(url=DISCORD_URL, content=header + chunk).execute()
                        time.sleep(1)
                    print("✅ 第二陣：AI攻略本(安定版)の送信完了！")
                else:
                    print(f"⚠️ AIは完全に沈黙しました (エラーコード: {response_fb.status_code})")
        except Exception as e:
            print(f"⚠️ AI通信エラー: {e}")
    else:
        print("💤 シグナル銘柄がないため、AI分析はスキップしました。")

if __name__ == "__main__":
    main()
