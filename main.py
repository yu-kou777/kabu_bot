import os
import sys
import datetime
import requests
import json
import numpy as np
import pandas as pd
import yfinance as yf
from google import genai
from google.genai import types

# ==========================================
# 1. 各種パラメータ設定 (出来高は緩め設定版)
# ==========================================
CONFIG = {
    "PRIME": {
        "MIN_AVG_VOLUME": 300000,    # 3ヶ月平均30万株以上に緩和
        "TODAY_VOL_RATIO": 1.5,      # 大引け後(16:00)の必要出来高倍率（1.5倍に緩和）
    },
    "STANDARD": {
        "MIN_AVG_VOLUME": 200000,    # 3ヶ月平均20万株に緩和
        "TODAY_VOL_RATIO": 1.5,      # 大引け後(16:00)の必要出来高倍率（1.5倍に緩和）
    },
    "BREAKOUT_RANGE": 0.05,          # 250日高値から5%以内、または上抜け
    "RCI_LONG_THRESHOLD": 50,        # テス流: 長期RCIが+50以上のトレンド継続
    "RSI_OVERHEAT": 85,              # RSIの極端な過熱（ダマシ）を排除する閾値
    "MIDDAY_VOL_MULTIPLIER": 0.6     # 11:00時点での前場ペース換算の必要出来高倍率
}

# 自動スクリーニング対象の銘柄プール（末尾に「.T」が必要です）
SAMPLE_TICKERS = {
    "5463.T": {"name": "丸一鋼管", "market": "PRIME"},
    "5702.T": {"name": "大紀アルミ", "market": "PRIME"},
    "5801.T": {"name": "古河電工", "market": "PRIME"},
    "7014.T": {"name": "名村造船所", "market": "STANDARD"},
    "6834.T": {"name": "精工技研", "market": "STANDARD"},
    "4107.T": {"name": "伊勢化学", "market": "STANDARD"},
    "6037.T": {"name": "楽待", "market": "PRIME"},
    "5803.T": {"name": "フジクラ", "market": "PRIME"},
    "4208.T": {"name": "UBE", "market": "PRIME"},
    "2695.T": {"name": "くら寿司", "market": "PRIME"}
}

# ==========================================
# 2. テクニカル指標の計算ロジック
# ==========================================
def calculate_rci(series, period):
    def _rci_chunk(chunk):
        n = len(chunk)
        if n < period:
            return np.nan
        time_rank = np.arange(1, n + 1)[::-1]
        price_rank = pd.Series(chunk).rank(method='min').values
        d_square = np.sum((time_rank - price_rank) ** 2)
        return (1 - (6 * d_square) / (n * (n**2 - 1))) * 100
    return series.rolling(window=period).apply(_rci_chunk, raw=True)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def calculate_dmi_adx(df, period=9):
    high, low, close = df['High'], df['Low'], df['Close']
    up_move, down_move = high.diff(), low.diff()
    p_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    m_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    p_di = (pd.Series(p_dm).rolling(window=period).mean() / (atr + 1e-10)) * 100
    m_di = (pd.Series(m_dm).rolling(window=period).mean() / (atr + 1e-10)) * 100
    return p_di.iloc[-1], m_di.iloc[-1]

def calculate_vwap(df):
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    pv = typical_price * df['Volume']
    return pv.rolling(window=25).sum() / (df['Volume'].rolling(window=25).sum() + 1e-10)

# ==========================================
# 3. 銘柄スクリーニング処理 (時間帯判定ロジック付き)
# ==========================================
def scan_markets(current_hour):
    matched_list = []
    
    # 11時か16時かで出来高の必要ハードルを自動調整
    is_midday = (current_hour == 11)
    
    for ticker, info in SAMPLE_TICKERS.items():
        market = info["market"]
        name = info["name"]
        param = CONFIG[market]
        
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1.5y")
            if len(df) < 250:
                continue
                
            today_close = df['Close'].iloc[-1]
            today_volume = df['Volume'].iloc[-1]
            avg_volume_3m = df['Volume'].iloc[-60:].mean()
            
            # 3ヶ月平均の最低流動性チェック
            if avg_volume_3m < param["MIN_AVG_VOLUME"]:
                continue
            
            # 出来高倍率の計算と判定（11時なら前場換算0.6倍、16時なら1.5倍）
            vol_ratio = today_volume / (avg_volume_3m + 1e-10)
            required_ratio = CONFIG["MIDDAY_VOL_MULTIPLIER"] if is_midday else param["TODAY_VOL_RATIO"]
            
            if vol_ratio < required_ratio:
                continue
                
            # 新高値判定
            high_250d = df['High'].iloc[-251:-1].max()
            distance_to_high = (today_close - high_250d) / high_250d
            
            if distance_to_high < -CONFIG["BREAKOUT_RANGE"]:
                continue
                
            # テクニカル指標計算
            df['RCI9'] = calculate_rci(df['Close'], 9)
            df['RCI27'] = calculate_rci(df['Close'], 27)
            df['RSI14'] = calculate_rsi(df['Close'], 14)
            df['VWAP25'] = calculate_vwap(df)
            
            rci9_today = df['RCI9'].iloc[-1]
            rci27_today = df['RCI27'].iloc[-1]
            rsi14_today = df['RSI14'].iloc[-1]
            vwap_today = df['VWAP25'].iloc[-1]
            p_di, m_di = calculate_dmi_adx(df, period=9)
            
            # テス流トレンド継続確認 & RSI過熱ダマシ排除
            if rci27_today < CONFIG["RCI_LONG_THRESHOLD"] or rsi14_today > CONFIG["RSI_OVERHEAT"]:
                continue
                
            vwap_gap = ((today_close - vwap_today) / vwap_today) * 100
            
            matched_list.append({
                "ticker": ticker.replace(".T", ""),
                "name": name,
                "market": market,
                "close": round(today_close, 1),
                "vol_ratio": round(vol_ratio, 2),
                "distance_high": round(distance_to_high * 100, 1),
                "rci9": round(rci9_today, 1),
                "rci27": round(rci27_today, 1),
                "rsi14": round(rsi14_today, 1),
                "vwap_gap": round(vwap_gap, 1),
                "dmi_signal": "買優位(+DI > -DI)" if p_di > m_di else "拮抗"
            })
            
        except Exception as e:
            print(f"Error scanning {ticker}: {e}")
            
    return matched_list

# ==========================================
# 4. Gemini API による生成AI分析 (時間帯を考慮)
# ==========================================
def get_gemini_analysis(matched_stocks, current_hour):
    try:
        client = genai.Client()
    except Exception as e:
        return f"Gemini初期化エラー: {e}"

    time_context = "【前場引け前(11:00時点)の途中経過判定】" if current_hour == 11 else "【大引け後(16:00時点)の確定判定】"

    if len(matched_stocks) > 0:
        prompt = f"""
        あなたはプロの機関投資家です。{time_context}として、以下の銘柄が「出来高を伴う250日新高値ブレイクの初動」としてスクリーニングされました。
        
        【検出銘柄データ】
        {json.dumps(matched_stocks, ensure_ascii=False, indent=2)}
        
        時間帯の性質（11時なら今日これからの追撃可能性、16時なら明日に向けた持ち越し期待）と、テクニカル面（RCI、RSI、VWAP乖離、DMI）の数値を踏まえ、どのような投資家心理で買われているのかを1銘柄につき3行程度で鋭く論評・解説してください。
        """
    else:
        prompt = f"""
        あなたはプロの機関投資家です。{time_context}のスクリーニングの結果、条件を満たす初動銘柄は「0件」でした。
        現在の地合い（押し目形成や様子見ムードなど）において投資家が今どのような心理状態にあり、なぜ無理にエントリーすべきではないのか、「テス流戦略」の視点を取り入れた相場解説・アドバイスを3〜4行で記述してください。
        """

    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7, max_output_tokens=800)
        )
        return response.text
    except Exception as e:
        return f"Gemini APIエラー: {e}"

# ==========================================
# 5. Discord Webhook へのメッセージ送信
# ==========================================
def send_to_discord(webhook_url, matched_stocks, ai_commentary, current_hour):
    current_date = datetime.date.today().strftime("%Y年%m%d日")
    time_title = "前場巡回スキャン (11:00)" if current_hour == 11 else "大引け確定スキャン (16:00)"
    
    if len(matched_stocks) > 0:
        embed_fields = []
        for s in matched_stocks:
            value_text = (
                f"**現在値/終値**: {s['close']}円\n"
                f"**出来高倍率**: `{s['vol_ratio']}倍` {'(前場換算)' if current_hour == 11 else ''}\n"
                f"**新高値まで**: {s['distance_high']}%\n"
                f"**RCI (9/27)**: `{s['rci9']}` / `{s['rci27']}`\n"
                f"**RSI / DMI**: RSI:{s['rsi14']} / {s['dmi_signal']}\n"
                f"**25日VWAP乖離**: {s['vwap_gap']}%"
            )
            embed_fields.append({"name": f"📌 {s['name']} ({s['ticker']}) [{s['market']}]", "value": value_text, "inline": False})
            
        payload = {
            "content": f"📡 **【新高値ブレイク初動アラート】** ({current_date} {time_title})",
            "embeds": [
                {"title": "🎯 条件合致銘柄リスト", "color": 15158332 if current_hour == 16 else 16753920, "fields": embed_fields},
                {"title": "💡 【Gemini's Eye】 AI時系列深掘り解説", "description": ai_commentary, "color": 3447003}
            ]
        }
    else:
        payload = {
            "content": f"📡 **【新高値ブレイク自動スクリーニング】** ({current_date} {time_title})",
            "embeds": [
                {"title": "❌ 該当銘柄は「0件」です", "description": f"現在、テス流・ハイブリッド新高値ブレイクの条件を満たす初動銘柄はありません。", "color": 9807270},
                {"title": "📊 【Gemini's Eye】 現在の相場心理と立ち回り", "description": ai_commentary, "color": 3447003}
            ]
        }

    requests.post(webhook_url, data=json.dumps(payload), headers={"Content-Type": "application/json"})

# ==========================================
# メイン実行処理
# ==========================================
if __name__ == "__main__":
    DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
    if not DISCORD_WEBHOOK_URL:
        sys.exit(1)
        
    # 現在の日本時間(JST)の「時」を取得
    # GitHub Actions上の環境変数としてJSTの時間を判定させます
    now_jst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    current_hour = now_jst.hour
    
    # 予期せぬ時間で動いた場合の安全弁（近い時間帯に丸める）
    if current_hour <= 12:
        exec_hour = 11
    else:
        exec_hour = 16
        
    print(f"=== スクリプト実行開始 (判定時間帯: {exec_hour}時) ===")
    
    matched_results = scan_markets(exec_hour)
    ai_analysis = get_gemini_analysis(matched_results, exec_hour)
    send_to_discord(DISCORD_WEBHOOK_URL, matched_results, ai_analysis, exec_hour)
    
    print("=== スクリプト処理終了 ===")

