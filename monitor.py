import yfinance as yf
import pandas as pd
import requests
import time
import numpy as np
import io
from datetime import datetime
import pytz
import jpholiday

# --- 設定 ---
# 【重要】新しいキーをセットしました。これをGitHub等に公開しないでください。
GEMINI_KEY = "AIzaSyBUiTPV-0yOXIDzgydV4NoArJkBufJSpys"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

VOLATILITY_THRESHOLD = 0.035 # 5日間で3.5%以上の値動きがある銘柄を抽出
PRICE_MIN = 500
MIN_VOLUME_5D = 100000

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    # 土日または祝日判定
    return now.weekday() >= 5 or jpholiday.is_holiday(now.date())

def get_target_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        target_df = df[df['市場・商品区分'].str.contains('プライム|スタンダード', na=False)]
        return {str(row['コード']) + ".T": f"{row['銘柄名']}({row['市場・商品区分'][:1]})" for _, row in target_df.iterrows()}
    except:
        # 通信エラー時のバックアップ
        return {"7203.T": "トヨタ(プ)", "8306.T": "三菱UFJ(プ)", "9984.T": "SBG(プ)"}

def get_rsi_vectorized(df, period):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss + 1e-9)))

def send_discord(text, title=None):
    if not text.strip(): return
    content = f"**【{title}】**\n{text}" if title else text
    try:
        # Discordへ送信
        requests.post(DISCORD_URL, json={"content": content}, timeout=10)
        time.sleep(1.2) # 連投制限対策
    except Exception as e:
        print(f"Discord送信エラー: {e}")

def get_ai_insight(msg_text):
    # 【404対策】最新の安定版エンドポイントを直接叩く
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    prompt = f"日本株プロとして以下の銘柄群から本命1つを厳選し、理由と目標値を100字以内で述べよ。:\n{msg_text}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.4}
    }
    try:
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=20)
        if res.status_code == 200:
            data = res.json()
            if "candidates" in data and data["candidates"]:
                return data["candidates"][0]["content"]["parts"][0]["text"]
        return f"AI分析スキップ (Status: {res.status_code})\n※銘柄リストを参考にしてください。"
    except:
        return "AI通信エラー：銘柄リストのテクニカル指標を優先してください。"

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print("🚀 高速スキャン開始（新キー・銘柄優先送信モード）...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    selected_list = []
    
    # チャンク分けしてデータ取得
    chunk_size = 120
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False, threads=True)
            close_df, high_df, low_df = data['Close'], data['High'], data['Low']
            rsi_df = get_rsi_vectorized(close_df, 9)

            for s in chunk:
                try:
                    c = close_df[s].dropna()
                    # 最低限のデータ量と株価のフィルタ
                    if len(c) < 50 or c.iloc[-1] < PRICE_MIN: continue
                    
                    # ボラティリティ判定（直近5日の高値と安値の幅）
                    high_5d = high_df[s].tail(5).max()
                    low_5d = low_df[s].tail(5).min()
                    vol = (high_5d - low_5d) / c.iloc[-1]
                    
                    cur_rsi = rsi_df[s].iloc[-1]

                    # 値動きが激しい銘柄をピックアップ
                    if vol >= VOLATILITY_THRESHOLD:
                        status = "🔥急騰" if cur_rsi > 70 else "❄️反発期待" if cur_rsi < 30 else "⚡活況"
                        info = f"・{name_map[s]} ({s}) 価:{c.iloc[-1]:,.0f} RSI:{cur_rsi:.0f} [{status}]"
                        selected_list.append((vol, info))
                except: continue
        except: continue
        time.sleep(1)

    if selected_list:
        # ボラティリティが高い順にソートして上位15件
        sorted_list = sorted(selected_list, key=lambda x: x[0], reverse=True)[:15]
        display_text = "\n".join([x[1] for x in sorted_list])
        
        # 💡【重要】まず銘柄リストを送信（AIの成否に関わらず必ず届く）
        send_discord(display_text, title="📊 本日の高ボラティリティ銘柄リスト")
        
        # 💡【次に】AIの短評を送信
        print("🤖 AI分析リクエスト中...")
        ai_input = "\n".join([x[1] for x in sorted_list[:5]]) # 上位5件をAIに渡す
        ai_msg = get_ai_insight(ai_input)
        send_discord(ai_msg, title="🤖 AIプロの厳選短評")
    else:
        send_discord("条件に合致する銘柄は見つかりませんでした。", title="🔍 スキャン完了")

    print("✅ 全ての工程が完了しました。")

if __name__ == "__main__":
    main()
