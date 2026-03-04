import yfinance as yf
import pandas as pd
import json
import os
import requests
import time
from datetime import datetime, timedelta, timezone

DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"
WATCHLIST_FILE = "jack_watchlist.json"

def send_discord(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def monitor_watchlist():
    if not os.path.exists(WATCHLIST_FILE): return
    with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
        watchlist = json.load(f)
    
    for item in watchlist:
        t = item['ticker']
        # 💡 GitHubからは少数の監視銘柄だけを取得
        try:
            data = yf.download(t, period="1d", interval="1m", progress=False)
            # アルゴ判定ロジック...
            # 判定がヒットしたらDiscordへ
        except:
            print(f"Skipping {t} due to error")
        time.sleep(5) # 慎重に

if __name__ == "__main__":
    monitor_watchlist()
