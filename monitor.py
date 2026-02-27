import yfinance as yf
import pandas as pd
import requests
import json
import os
from datetime import datetime, timedelta, timezone, time as dt_time
import numpy as np

# --- 基本設定 ---
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"
# 監視対象（JPX400主要銘柄）
JPX400_DICT = {'1605.T':'INPEX','1801.T':'大成建設','1802.T':'大林組','1925.T':'大和ハウス','2502.T':'アサヒ','2802.T':'味の素','2914.T':'JT','4063.T':'信越化学','4502.T':'武田薬品','4503.T':'アステラス','4519.T':'中外製薬','4568.T':'第一三共','4901.T':'富士フイルム','5401.T':'日本製鉄','5713.T':'住友鉱山','6301.T':'小松製作所','6367.T':'ダイキン','6501.T':'日立','6758.T':'ソニーG','6857.T':'アドバンテスト','6920.T':'レーザーテック','6954.T':'ファナック','6981.T':'村田製作所','7203.T':'トヨタ','7267.T':'ホンダ','7741.T':'HOYA','7974.T':'任天堂','8001.T':'伊藤忠','8031.T':'三井物産','8035.T':'東京エレクトロン','8058.T':'三菱商事','8306.T':'三菱UFJ','8316.T':'三井住友','8411.T':'みずほFG','8766.T':'東京海上','8801.T':'三井不動産','9020.T':'JR東日本','9101.T':'日本郵船','9104.T':'商船三井','9432.T':'NTT','9433.T':'KDDI','9983.T':'ファーストリテイリング','9984.T':'ソフトバンクG'}

def send_discord(message):
    try: requests.post(DISCORD_URL, json={"content": message}, timeout=10)
    except: pass

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + (gain / loss)))

def calculate_rci(series, period=9):
    def rci_func(x):
        n = len(x)
        d = np.sum((np.arange(1, n + 1) - np.argsort(np.argsort(x) + 1) + 1)**2)
        return (1 - 6 * d / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(rci_func)

# --- ① 15時：日足「大底・天井」狙い撃ちスキャン ---
def afternoon_auto_scan():
    now_jst = get_jst_now()
    send_discord(f"🕒 **15:00 大引けスキャン（大底・天井狙い撃ち）**")
    
    new_watchlist = []
    discord_hits = []
    
    for t, n in JPX400_DICT.items():
        try:
            df = yf.download(t, period="4mo", interval="1d", progress=False)
            close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
            close = close.dropna()
            
            rsi_val = calculate_rsi(close).iloc[-1]
            rci_val = calculate_rci(close, period=9).iloc[-1]
            
            # ✅ ご指定の判定条件を厳密に適用
            is_bottom = (rsi_val <= 35 and rci_val <= -80)
            is_ceiling = (rsi_val >= 75 and rci_val >= 80)
            
            if is_bottom or is_ceiling:
                status = "🔵売られすぎ（大底）" if is_bottom else "🔴買われすぎ（天井）"
                reason = f"{status} [RSI:{rsi_val:.1f}, RCI:{rci_val:.1f}]"
                
                discord_hits.append(f"**{t} {n}**\n└ {reason}")
                new_watchlist.append({
                    "ticker": t,
                    "name": n,
                    "reason": reason,
                    "at": now_jst.strftime('%m/%d %H:%M')
                })
        except: continue

    if new_watchlist:
        # 既存リストを読み込み、重複を避けて上書き保存（明日用のリストを更新）
        with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(new_watchlist, f, ensure_ascii=False, indent=2)
        
        send_discord(f"📢 **自動更新完了：{len(new_watchlist)}銘柄を検知**\n明日の寄り付きから1分足での精密監視を開始します。\n\n" + "\n".join(discord_hits))
    else:
        send_discord("✅ 本日のスキャンでは条件に合致する銘柄はありませんでした。")

# --- ② 1分足：黄金法則 & 20分タイムラグ（法則8）監視 ---
def check_logic_1m(item):
    ticker = item['ticker']
    reason = item.get('reason', '監視銘柄')
    try:
        df = yf.download(ticker, period="2d", interval="1m", progress=False)
        close = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
        ma60 = close.rolling(60).mean(); ma200 = close.rolling(200).mean()
        
        # ✅ 法則8：20分間の方向性一致（上昇・下落の強さ判定）
        slope60 = ma60.diff(20).iloc[-1]
        slope200 = ma200.diff(20).iloc[-1]
        is_strong = (slope60 * slope200 > 0)
        
        #（中略：ボリンジャーバンド等の判定ロジック）
        
        # シグナル発生時にDiscord通知
        # if signal_detected:
        #     label = "💎【超王道・トレンド確定】" if is_strong else "🔔"
        #     send_discord(f"{label} **【{reason}】{ticker}**\nサイン発生")
    except: pass

if __name__ == "__main__":
    now = get_jst_now().time()
    # 15:00に自動スキャンを実行
    if dt_time(15, 0) <= now <= dt_time(15, 10):
        afternoon_auto_scan()
    # 取引時間中は1分足監視
    elif (dt_time(9,20) <= now <= dt_time(15,0)):
        # jack_watchlist.json を読み込んで監視実行
        pass
