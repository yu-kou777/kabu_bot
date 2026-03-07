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

def get_prime_tickers():
    """JPX公式からプライム市場の銘柄リストを取得"""
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
        # 失敗した時のためのフォールバック（緊急用）
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
    
    # 1. 株価データを一括ダウンロード（高速化）
    print("📡 株価データを一括ダウンロード中 (約1〜2分かかります)...")
    # yfinanceの仕様上、大量ダウンロードの進行状況が表示されます
    data = yf.download(tickers_list, period="6mo", threads=True, progress=False)
    close_prices = data['Close']
    
    # 💡 抽出グループ（Discordパンク防止のため、強いシグナルのみ厳選）
    groups = {
        "🔥【大底急騰期待】RCI最低値圏(-95以下) ＆ RSI20以下": [],
        "⚠️【急落警戒】RCI最高値圏(95以上) ＆ RSI80以上": [],
        "🟢【買い推奨】RSI30以下 ＆ RCI-50以下": [],
        "🔴【空売り推奨】RSI90以上 ＆ RCI95以上": [],
        "🚀【急騰期待】RSI10以下": [],
        "⤴️【反転シグナル】RSI・RCI同時に売られすぎ圏から上向き": []
    }
    
    print("⚙️ テクニカル指標を計算中...")
    # 2. 各銘柄の計算と判定
    for symbol, name in TICKERS.items():
        try:
            if symbol not in close_prices.columns: continue
            series = close_prices[symbol].dropna()
            if len(series) < 15: continue
            
            rsi = round(calculate_rsi(series, 14).iloc[-1], 1)
            rci = round(calculate_rci(series, 9)[-1], 1)
            prev_rsi = round(calculate_rsi(series, 14).iloc[-2], 1)
            prev_rci = round(calculate_rci(series, 9)[-2], 1)
            price = f"{series.iloc[-1]:,.0f}"
            
            info_str = f"  ・{name} ({symbol}): RSI {rsi} / RCI {rci} [{price}円]"
            
            # 厳格なAND条件判定
            if rci <= -95 and rsi <= 20:
                groups["🔥【大底急騰期待】RCI最低値圏(-95以下) ＆ RSI20以下"].append(info_str)
            elif rci >= 95 and rsi >= 80:
                groups["⚠️【急落警戒】RCI最高値圏(95以上) ＆ RSI80以上"].append(info_str)
            elif rsi <= 30 and rci <= -50:
                groups["🟢【買い推奨】RSI30以下 ＆ RCI-50以下"].append(info_str)
            elif rsi >= 90 and rci >= 95:
                groups["🔴【空売り推奨】RSI90以上 ＆ RCI95以上"].append(info_str)
            elif rsi <= 10:
                groups["🚀【急騰期待】RSI10以下"].append(info_str)
            elif (rci <= -50 and prev_rci < rci) and (rsi <= 30 and prev_rsi < rsi):
                groups["⤴️【反転シグナル】RSI・RCI同時に売られすぎ圏から上向き"].append(info_str)
        except:
            pass

    # 3. Discord送信用のメッセージ構築
    now_str = datetime.now().strftime('%m/%d %H:%M')
    data_msg = f"📊 **【Jack株AI プライム全市場 スキャン速報】** ({now_str})\n\n"
    has_signals = False
    
    for group_name, stocks in groups.items():
        if stocks:
            has_signals = True
            data_msg += f"**{group_name}** ({len(stocks)}銘柄)\n"
            for stock in stocks:
                data_msg += f"{stock}\n"
            data_msg += "\n"
            
    if not has_signals:
        data_msg += "現在、プライム市場で指定の強力なシグナルに合致する銘柄はありません。\n"

    # 【第一陣】速報をDiscordへ送信
    try:
        for i in range(0, len(data_msg), 1900):
            DiscordWebhook(url=DISCORD_URL, content=data_msg[i:i+1900]).execute()
            time.sleep(1)
        print("✅ 第一陣：戦略シグナル速報の送信完了！")
    except Exception as e:
        print(f"❌ 速報の送信に失敗: {e}")

    # 4. 【第二陣】AIにシグナル銘柄だけを分析させる
    if has_signals:
        print("🤖 AIがシグナル抽出銘柄の攻略本を執筆中...")
        prompt = f"日本株プロとしてテクニカル分析せよ。以下のプライム市場のシグナル点灯銘柄について、変動要因、上昇期待日、目標株価を銘柄ごとに3行で簡潔に分析せよ。\n\n{data_msg}"
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            headers = {'Content-Type': 'application/json'}
            data = {"contents": [{"parts": [{"text": prompt}]}]}
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                ai_analysis = response.json()['candidates'][0]['content']['parts'][0]['text']
                ai_msg = f"🤖 **【AI攻略本 (プライム厳選)】**\n\n{ai_analysis}"
                
                for i in range(0, len(ai_msg), 1900):
                    DiscordWebhook(url=DISCORD_URL, content=ai_msg[i:i+1900]).execute()
                    time.sleep(1)
                print("✅ 第二陣：AI攻略本の送信完了！")
            else:
                print(f"⚠️ AIは裏方で沈黙しました (エラーコード: {response.status_code})")
        except:
            print("⚠️ AI通信エラーのため裏方で処理を終了します。")
    else:
        print("💤 シグナル銘柄がないため、AI分析はスキップしました。")

if __name__ == "__main__":
    main()
