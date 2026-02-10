import os
import yfinance as yf
import pandas as pd
import requests
import json
import datetime

# ==========================================
# ⚙️ 設定 (GitHubの金庫から読み込む)
# ==========================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_URL")
SHEET_ID = os.environ.get("SHEET_ID")

# ==========================================
# 🛠️ 関数群
# ==========================================
def get_settings():
    """スプレッドシートから設定を読み込む"""
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
        df = pd.read_csv(url, header=None, dtype=str).fillna("")
        
        # モード (B1)
        mode = "SWING"
        if len(df) > 0 and len(df.columns) > 1:
            val = str(df.iloc[0, 1]).strip().upper()
            if "DAY" in val: mode = "DAY"
            
        # 銘柄 (A3以降)
        tickers = []
        if len(df) > 2:
            raw = df.iloc[2:, 0].tolist()
            for t in raw:
                t = str(t).strip()
                if t.isdigit(): tickers.append(f"{t}.T")
                elif t: tickers.append(t)
        
        return mode, tickers
    except Exception as e:
        print(f"Sheet Error: {e}")
        return "SWING", []

def send_discord(msg, mode):
    if not DISCORD_WEBHOOK_URL: return
    icon = "🐇" if mode == "DAY" else "🐢"
    data = {"content": f"{icon} {msg}"}
    requests.post(DISCORD_WEBHOOK_URL, headers={"Content-Type": "application/json"}, data=json.dumps(data))

def check_market():
    mode, watch_list = get_settings()
    if not watch_list: return

    print(f"Mode: {mode}, Tickers: {len(watch_list)}")
    report_msgs = []

    for ticker in watch_list:
        try:
            stock = yf.Ticker(ticker)
            
            # データ取得期間
            period = "1y" if mode == "SWING" else "5d"
            interval = "1d" if mode == "SWING" else "5m"
            hist = stock.history(period=period, interval=interval)
            
            if len(hist) < 30: continue

            # 指標計算
            close = hist['Close']
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = 100 - (100 / (1 + gain/loss))
            
            # SMA
            sma_s = close.rolling(25).mean()
            sma_l = close.rolling(75).mean()

            # 最新値
            curr = hist.iloc[-1]
            prev = hist.iloc[-2]
            curr_rsi = rsi.iloc[-1]
            prev_rsi = rsi.iloc[-2]
            
            # --- 判定ロジック ---
            price_str = f"{curr['Close']:,.0f}"
            
            # 閾値設定
            buy_th = 30 if mode == "SWING" else 25
            sell_th = 70 if mode == "SWING" else 75

            # 1. ゴールデンクロス
            if sma_s.iloc[-2] < sma_l.iloc[-2] and sma_s.iloc[-1] > sma_l.iloc[-1]:
                report_msgs.append(f"🚀 **{ticker}** ゴールデンクロス ({price_str}円)")

            # 2. RSI 買い
            if curr_rsi <= buy_th:
                report_msgs.append(f"✨ **{ticker}** 買い時 RSI:{curr_rsi:.1f} ({price_str}円)")
            
            # 3. RSI 売り
            if curr_rsi >= sell_th:
                report_msgs.append(f"📉 **{ticker}** 売り時 RSI:{curr_rsi:.1f} ({price_str}円)")

        except Exception as e:
            print(f"Err {ticker}: {e}")

    if report_msgs:
        send_discord("\n".join(report_msgs), mode)
    else:
        print("No signals.")

if __name__ == "__main__":
    check_market()
