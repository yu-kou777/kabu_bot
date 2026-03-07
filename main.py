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

TICKERS = {
    "8035.T": "東京エレクトロン", "9984.T": "ソフトバンクG", "6758.T": "ソニーG",
    "7203.T": "トヨタ自動車", "6920.T": "レーザーテック", "6857.T": "アドバンテスト",
    "6146.T": "ディスコ", "4063.T": "信越化学", "8058.T": "三菱商事",
    "8316.T": "三井住友FG", "9101.T": "日本郵船", "7011.T": "三菱重工",
    "4502.T": "武田薬品", "6501.T": "日立製作所", "6702.T": "富士通",
    "6201.T": "豊田自動織機", "9104.T": "商船三井", "6367.T": "ダイキン工業",
    "6273.T": "SMC", "7974.T": "任天堂", "9020.T": "JR東日本",
    "2914.T": "JT", "4061.T": "デンカ", "6723.T": "ルネサス"
}

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
    print("🚀 ジャック株AI：戦闘開始...")
    
    # 💡 ジャックさんのメモに基づくグループ分け辞書
    groups = {
        "🔥【大底急騰期待】RCI最低値圏(-95以下) ＆ RSI20以下": [],
        "⚠️【急落警戒】RCI最高値圏(95以上) ＆ RSI80以上": [],
        "🟢【買い推奨】RSI30以下 ＆ RCI-50以下": [],
        "🔴【空売り推奨】RSI90以上 ＆ RCI95以上": [],
        "🚀【急騰期待】RSI10以下": [],
        "⤴️【反転シグナル】RSI・RCI同時に売られすぎ圏から上向き": []
    }
    
    # 1. データ収集と判定
    for symbol, name in TICKERS.items():
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period="6mo")
            if df.empty or len(df) < 2: continue
            
            # 当日と前日のデータを取得
            rsi = round(calculate_rsi(df['Close'], 14).iloc[-1], 1)
            rci = round(calculate_rci(df['Close'], 9)[-1], 1)
            prev_rsi = round(calculate_rsi(df['Close'], 14).iloc[-2], 1)
            prev_rci = round(calculate_rci(df['Close'], 9)[-2], 1)
            price = f"{df['Close'].iloc[-1]:,.0f}"
            
            info_str = f"  ・{name} ({symbol}): RSI {rsi} / RCI {rci} [{price}円]"
            
            # --- 厳格なAND条件判定（上から優先して判定） ---
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
            # メモの「同時にデッドクロスが買い時」は、「両指標が売られすぎ圏で同時に反転上昇した瞬間」と解釈
            elif (rci <= -50 and prev_rci < rci) and (rsi <= 30 and prev_rsi < rsi):
                groups["⤴️【反転シグナル】RSI・RCI同時に売られすぎ圏から上向き"].append(info_str)
                
        except:
            pass

    # 2. Discord送信用のメッセージ構築
    now_str = datetime.now().strftime('%m/%d %H:%M')
    data_msg = f"📊 **【Jack株AI 戦略シグナル速報】** ({now_str})\n\n"
    has_signals = False
    
    # 該当する銘柄があるグループだけをテキストに追加
    for group_name, stocks in groups.items():
        if stocks:
            has_signals = True
            data_msg += f"**{group_name}**\n"
            for stock in stocks:
                data_msg += f"{stock}\n"
            data_msg += "\n"
            
    if not has_signals:
        data_msg += "現在、指定のシグナルに合致する銘柄はありません。\n"

    # 【第一陣】グループ分けされた速報を確実にDiscordへ送信
    try:
        for i in range(0, len(data_msg), 1900):
            DiscordWebhook(url=DISCORD_URL, content=data_msg[i:i+1900]).execute()
            time.sleep(1)
        print("✅ 第一陣：戦略シグナル速報の送信完了！")
    except Exception as e:
        print(f"❌ 速報の送信に失敗: {e}")

    # 3. 【第二陣】AIに裏方で攻略本を執筆させる（シグナル銘柄のみ分析）
    if has_signals:
        print("🤖 AIがシグナル銘柄の攻略本を執筆中...")
        prompt = f"日本株プロとして分析。以下のシグナルが出ている銘柄の変動要因、上昇期待日、目標株価を銘柄ごとに3行で簡潔に分析せよ。\n\n{data_msg}"
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            headers = {'Content-Type': 'application/json'}
            data = {"contents": [{"parts": [{"text": prompt}]}]}
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 200:
                ai_analysis = response.json()['candidates'][0]['content']['parts'][0]['text']
                ai_msg = f"🤖 **【AI攻略本】**\n\n{ai_analysis}"
                
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
