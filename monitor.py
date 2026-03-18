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
GEMINI_KEY = "AIzaSyBUiTPV-0yOXIDzgydV4NoArJkBufJSpys"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

VOLATILITY_THRESHOLD = 0.035 
PRICE_MIN = 500
MIN_VOLUME_5D = 100000

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
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
        return {"7203.T": "トヨタ", "8306.T": "三菱UFJ", "9984.T": "SBG"}

def get_rsi_vectorized(df, period):
    delta = df.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss + 1e-9)))

def send_discord(text, title=None):
    if not text.strip(): return
    content = f"**【{title}】**\n{text}" if title else text
    try:
        requests.post(DISCORD_URL, json={"content": content}, timeout=10)
        time.sleep(1.2)
    except Exception as e:
        print(f"Discord送信エラー: {e}")

def get_ai_insight(msg_text):
    # エンドポイント
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    payload = {"contents": [{"parts": [{"text": f"株プロとして1銘柄厳選し短評せよ:\n{msg_text}"}]}]}
    try:
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        return None # 404等の場合はNoneを返してシステム選定に切り替える
    except:
        return None

def main():
    if is_market_holiday():
        print("☕ 本日は休場です。")
        return

    print("🚀 スキャン開始（AIバックアップ・システム選定搭載）...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    selected_list = []
    
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
                    if len(c) < 50 or c.iloc[-1] < PRICE_MIN: continue
                    
                    vol = (high_df[s].tail(5).max() - low_df[s].tail(5).min()) / c.iloc[-1]
                    cur_rsi = rsi_df[s].iloc[-1]

                    if vol >= VOLATILITY_THRESHOLD:
                        info = f"・{name_map[s]} ({s}) 価:{c.iloc[-1]:,.0f} RSI:{cur_rsi:.0f}"
                        # 乖離率やRSI、ボラティリティをスコア化して保存
                        score = vol * (1 + abs(50 - cur_rsi) / 100) 
                        selected_list.append({"info": info, "score": score, "rsi": cur_rsi})
                except: continue
        except: continue
        time.sleep(1)

    if selected_list:
        # スコア順にソート
        sorted_list = sorted(selected_list, key=lambda x: x['score'], reverse=True)
        display_text = "\n".join([x['info'] for x in sorted_list[:15]])
        
        # 1. 銘柄リストを送信
        send_discord(display_text, title="📊 本日の高ボラティリティ銘柄リスト")
        
        # 2. AI短評の取得（失敗したらシステムによる自動選定を表示）
        print("🤖 分析を実行中...")
        ai_msg = get_ai_insight(display_text[:500])
        
        if ai_msg:
            send_discord(ai_msg, title="🤖 AIプロの厳選短評")
        else:
            # AIが404で落ちた場合のバックアップロジック
            best = sorted_list[0]
            reason = "ボラティリティ最大" if best['rsi'] > 30 else "売られすぎからのリバウンド狙い"
            backup_msg = f"【システム選定本命】\n{best['info']}\n理由：スコア最高値。{reason}。AI通信エラーのためシステムが自動選定しました。"
            send_discord(backup_msg, title="⚙️ システムによる自動厳選")
    else:
        send_discord("条件に合う銘柄はありませんでした。", title="🔍 スキャン完了")

    print("✅ 全工程完了")

if __name__ == "__main__":
    main()

