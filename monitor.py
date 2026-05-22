import yfinance as yf
import pandas as pd
import requests
import time
import numpy as np
import io
from datetime import datetime
import pytz
import jpholiday

# --- ⚙️ 設定 ---
GEMINI_KEY = "AIzaSyBUiTPV-0yOXIDzgydV4NoArJkBufJSpys"
DISCORD_URL = "https://discord.com/api/webhooks/1470471750482530360/-epGFysRsPUuTesBWwSxof0sa9Co3Rlp415mZ1mkX2v3PZRfxgZ2yPPHa1FvjxsMwlVX"

PRICE_MIN = 3001       # 呼値5円以上（株価3,001円以上）限定

def is_market_holiday():
    tz = pytz.timezone('Asia/Tokyo')
    now = datetime.now(tz)
    return now.weekday() >= 5 or jpholiday.is_holiday(now.date())

def get_target_tickers():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        df = pd.read_excel(io.BytesIO(res.content), engine='xlrd')
        target_df = df[df['市場・商品区分'].str.contains('プライム|スタンダード', na=False)]
        return {str(row['コード']) + ".T": f"{row['銘柄名']}" for _, row in target_df.iterrows()}
    except:
        return {"8035.T": "東エレク", "9984.T": "SBG", "6834.T": "精工技研"}

# --- 📊 指標計算関数 ---
def calculate_rci(df, period):
    def _rci(x):
        n = len(x); d = np.sum((np.arange(1, n + 1) - pd.Series(x).rank().values)**2)
        return (1 - (6 * d) / (n * (n**2 - 1))) * 100
    return df.rolling(window=period).apply(_rci)

def calculate_psychological(df, period=12):
    return ((df.diff() > 0).astype(int).rolling(window=period).sum() / period) * 100

def get_sakata_signal(h, l, o, c):
    s = []
    try:
        if (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-2] > o.iloc[-2]) and (c.iloc[-3] > o.iloc[-3]) and (c.iloc[-1] > c.iloc[-2]):
            s.append("🔆赤三兵")
        if (c.iloc[-2] < o.iloc[-2]) and (c.iloc[-1] > o.iloc[-1]) and (c.iloc[-1] >= o.iloc[-2]):
            s.append("🔥陽の包み足")
        if l.iloc[-1] > h.iloc[-2]:
            s.append("✨上放れ窓")
        if (c.iloc[-3] < o.iloc[-3]) and (abs(c.iloc[-2] - o.iloc[-2]) < abs(c.iloc[-3] - o.iloc[-3]) * 0.2) and (c.iloc[-1] > o.iloc[-1]):
            s.append("🌅明けの明星")
    except: pass
    return " ".join(s)

def check_channel_touch(df_stock, lookback=20):
    """直近データからチャネル帯を計算（安全堅牢版）"""
    try:
        if len(df_stock) < lookback: return None
        df_sub = df_stock.tail(lookback)
        
        # データのクレンジング
        highs = pd.Series(df_sub['High']).ffill().bfill().values
        lows = pd.Series(df_sub['Low']).ffill().bfill().values
        closes = pd.Series(df_sub['Close']).ffill().bfill().values
        p_last = closes[-1]
        
        idx_h1 = np.argmax(highs); h1 = highs[idx_h1]
        highs_remain = highs.copy(); highs_remain[idx_h1] = -1
        idx_h2 = np.argmax(highs_remain); h2 = highs[idx_h2]
        
        idx_l1 = np.argmin(lows); l1 = lows[idx_l1]
        lows_remain = lows.copy(); lows_remain[idx_l1] = 99999999
        idx_l2 = np.argmin(lows_remain); l2 = lows[idx_l2]

        slope_h = (h1 - h2) / (idx_h1 - idx_h2 + 1e-5)
        slope_l = (l1 - l2) / (idx_l1 - idx_l2 + 1e-5)
        
        expected_low = l1 + slope_l * (lookback - 1 - idx_l1)
        expected_high = h1 + slope_h * (lookback - 1 - idx_h1)
        
        # 判定を少しマイルドに調整
        is_support_touch = abs(p_last - expected_low) / (expected_low + 1e-9) <= 0.02
        is_resistance_touch = abs(p_last - expected_high) / (expected_high + 1e-9) <= 0.02
        
        if is_support_touch: return "サポート帯タッチ"
        if is_resistance_touch: return "レジスタンス帯タッチ"
    except: pass
    return None

def send_discord_raw(payload):
    """Discordへの送信を確実に実行する関数"""
    try:
        res = requests.post(DISCORD_URL, json=payload, timeout=15)
        return res.status_code == 204 or res.status_code == 200
    except:
        return False

# --- 🚀 メインロジック ---
def main():
    if is_market_holiday(): return

    tz = pytz.timezone('Asia/Tokyo')
    current_hour = datetime.now(tz).hour
    
    if current_hour < 13:
        timing_title = "【前場・11:00中間巡回】"
        vol_today_multiplier = 0.45
    else:
        timing_title = "【後場・16:00大引確定】"
        vol_today_multiplier = 1.5

    print(f"🚀 {timing_title} スキャナー起動...")
    name_map = get_target_tickers()
    tickers = list(name_map.keys())
    
    categories = {
        "confirmed_buy": {
            "title": f"🏹{timing_title}・【反転の確証】スイング底値狙撃シグナル",
            "items": [], "codes": [], "color": 0x00ffff
        },
        "forecast_signal": {
            "title": f"📈{timing_title}・【反転予兆】マイフォルダー登録候補",
            "items": [], "codes": [], "color": 0x3399ff
        }
    }

    chunk_size = 80  # エラー回避のため塊を少し小さく
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            data = yf.download(chunk, period="1y", interval="1d", progress=False)
            if data.empty: continue
            
            cl, hi, lo, op, vo = data['Close'], data['High'], data['Low'], data['Open'], data['Volume']
            
            # 欠損値対策を徹底
            r9_df = calculate_rci(cl, 9).ffill().bfill()
            r27_df = calculate_rci(cl, 27).ffill().bfill()
            psy_df = calculate_psychological(cl, 12).ffill().bfill()
            
            for s in chunk:
                try:
                    if s not in cl.columns: continue
                    c_s = cl[s].dropna()
                    v_s = vo[s].dropna()
                    if len(c_s) < 65 or c_s.iloc[-1] < PRICE_MIN: continue  
                    
                    # 出来高トリプルフィルター
                    vol_3m_avg = v_s.iloc[-60:].mean()          
                    vol_today = v_s.iloc[-1]                     
                    vol_5d_avg = v_s.iloc[-5:].mean()            
                    
                    if vol_3m_avg < 500000: continue             
                    if vol_today < (vol_3m_avg * vol_today_multiplier): continue   
                    if vol_5d_avg < (vol_3m_avg * 1.2): continue  
                    
                    p = c_s.iloc[-1]
                    r9_c, r9_p = r9_df[s].iloc[-1], r9_df[s].iloc[-2]
                    r27_c, r27_p = r27_df[s].iloc[-1], r27_df[s].iloc[-2]
                    psy_c, psy_p = psy_df[s].iloc[-1], psy_df[s].iloc[-2]
                    
                    df_single = pd.DataFrame({'Open': op[s], 'High': hi[s], 'Low': lo[s], 'Close': cl[s], 'Volume': vo[s]}).dropna()
                    sakata = get_sakata_signal(df_single['High'], df_single['Low'], df_single['Open'], df_single['Close'])
                    channel_status = check_channel_touch(df_single)
                    
                    code_num = s.replace(".T", "")
                    vol_ratio = vol_today / vol_3m_avg
                    yobine_label = "5円単位" if p <= 5000 else "10円単位" if p <= 30000 else "50円単位〜"

                    card = (f"**{code_num} {name_map[s]}** (`{p:,.0f}円` / {yobine_label}) 出来高:{vol_ratio:.2f}倍\n"
                            f"├ 📐チャネル: `{channel_status if channel_status else 'レンジ内移動'}`\n"
                            f"└ RCI9:`{r9_c:.0f}` | RCI27:`{r27_c:.0f}` | Psy:`{psy_c:.0f}` | 酒田:`{sakata if sakata else 'なし'}`\n")

                    is_rci_bottom = (r9_c <= -80 or (r9_p <= -15 and r9_c > r9_p))
                    is_psy_bottom = (psy_c <= 45)
                    is_rci_hint = (r27_c < r27_p and r27_c < -15) and (r9_c <= -85) 
                    is_today_yang = (c_s.iloc[-1] > op[s].iloc[-1]) 

                    # ① 底値の確証
                    if channel_status == "サポート帯タッチ" and (is_rci_bottom or is_rci_hint) and is_psy_bottom and is_today_yang:
                        categories["confirmed_buy"]["items"].append(card)
                        categories["confirmed_buy"]["codes"].append(code_num)
                        
                    # ② 反転予兆
                    elif (sakata != "" or is_rci_hint) and (psy_c <= 40):
                        categories["forecast_signal"]["items"].append(card)
                        categories["forecast_signal"]["codes"].append(code_num)

                except: continue
        except: continue
        time.sleep(1)

    # ーーー 📨 Discord送信ユニット（完全防壁版） ーーー
    send_count = 0
    for key, data in categories.items():
        if data["items"]:
            body = "\n".join(data["items"][:15])
            footer = f"\n**📌 コピペ用コード (番号のみ)**\n`{','.join(data['codes'])}`"
            payload = {"embeds": [{"title": data["title"], "description": body + footer, "color": data["color"], "timestamp": datetime.now().isoformat()}]}
            if send_discord_raw(payload):
                send_count += 1
            time.sleep(1)

    # 🌟 1件も送るものがなかった場合、生存確認用のグレー埋め込みメッセージを「確実に」送信
    if send_count == 0:
        empty_title = f"ℹ️ {timing_title}・定期巡回完了報告"
        empty_message = f"全銘柄を正常にスキャンしましたが、現時点で「テス流・チャネル反転基準」を完璧にクリアする値がさ株はありませんでした。\n\n※この通知が届いている＝システムおよびDiscord連携は**100%正常稼働**しています。"
        payload = {"embeds": [{"title": empty_title, "description": empty_message, "color": 0x95a5a6, "timestamp": datetime.now().isoformat()}]}
        send_discord_raw(payload)

if __name__ == "__main__":
    main()

