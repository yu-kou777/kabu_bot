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
        "TODAY_VOL_RATIO": 1.5,      # 当日出来高1.5倍以上に緩和
    },
    "STANDARD": {
        "MIN_AVG_VOLUME": 200000,    # 3ヶ月平均20万株に緩和
        "TODAY_VOL_RATIO": 1.5,      # 当日出来高1.5倍以上に緩和
    },
    "BREAKOUT_RANGE": 0.05,          # 250日高値から5%以内、または上抜け
    "RCI_LONG_THRESHOLD": 50,        # テス流: 長期RCIが+50以上のトレンド継続
    "RSI_OVERHEAT": 85               # RSIの極端な過熱（ダマシ）を排除する閾値
}

# 毎日自動スクリーニングを行いたい銘柄プール
# ※ yfinanceで取得するため、末尾に「.T」が必要です。
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
# 2. テクニカル指標の自作計算ロジック
# ==========================================
def calculate_rci(series, period):
    """順位相関係数 (RCI) の計算"""
    def _rci_chunk(chunk):
        n = len(chunk)
        if n < period:
            return np.nan
        time_rank = np.arange(1, n + 1)[::-1]  # 時間の順位（直近が1）
        price_rank = pd.Series(chunk).rank(method='min').values  # 価格の順位
        d_square = np.sum((time_rank - price_rank) ** 2)
        rci = (1 - (6 * d_square) / (n * (n**2 - 1))) * 100
        return rci

    return series.rolling(window=period).apply(_rci_chunk, raw=True)

def calculate_rsi(series, period=14):
    """RSI の計算"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def calculate_dmi_adx(df, period=9):
    """テス流カスタム: 期間9日で感度を高めたDMIの計算"""
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    up_move = high.diff()
    down_move = low.diff()
    
    p_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    m_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(window=period).mean()
    p_di = (pd.Series(p_dm).rolling(window=period).mean() / (atr + 1e-10)) * 100
    m_di = (pd.Series(m_dm).rolling(window=period).mean() / (atr + 1e-10)) * 100
    
    return p_di.iloc[-1], m_di.iloc[-1]

def calculate_vwap(df):
    """25日価格出来高平均 (VWAP) の計算"""
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    pv = typical_price * df['Volume']
    cum_pv = pv.rolling(window=25).sum()
    cum_vol = df['Volume'].rolling(window=25).sum()
    return cum_pv / (cum_vol + 1e-10)

# ==========================================
# 3. 銘柄スクリーニング処理
# ==========================================
def scan_markets():
    matched_list = []
    
    for ticker, info in SAMPLE_TICKERS.items():
        market = info["market"]
        name = info["name"]
        param = CONFIG[market]
        
        print(f"Scanning: {name} ({ticker}) [{market}]...")
        
        try:
            # 250日高値を判定するため、過去1.5年分のデータを取得
            stock = yf.Ticker(ticker)
            df = stock.history(period="1.5y")
            if len(df) < 250:
                continue
                
            today_close = df['Close'].iloc[-1]
            today_volume = df['Volume'].iloc[-1]
            
            # ① 出来高フィルター（3ヶ月平均の条件緩和）
            avg_volume_3m = df['Volume'].iloc[-60:].mean()
            if avg_volume_3m < param["MIN_AVG_VOLUME"]:
                continue
            
            # ② 当日出来高急増フィルター（1.5倍に条件緩和）
            vol_ratio = today_volume / (avg_volume_3m + 1e-10)
            if vol_ratio < param["TODAY_VOL_RATIO"]:
                continue
                
            # ③ 新高値ブレイク判定（過去250日の最高値と比較）
            high_250d = df['High'].iloc[-251:-1].max()
            distance_to_high = (today_close - high_250d) / high_250d
            
            # 高値から5%以内、または上抜けているか
            if distance_to_high < -CONFIG["BREAKOUT_RANGE"]:
                continue
                
            # ④ テス流テクニカル指標の計算
            df['RCI9'] = calculate_rci(df['Close'], 9)
            df['RCI27'] = calculate_rci(df['Close'], 27)
            df['RSI14'] = calculate_rsi(df['Close'], 14)
            df['VWAP25'] = calculate_vwap(df)
            
            rci9_today = df['RCI9'].iloc[-1]
            rci27_today = df['RCI27'].iloc[-1]
            rsi14_today = df['RSI14'].iloc[-1]
            vwap_today = df['VWAP25'].iloc[-1]
            p_di, m_di = calculate_dmi_adx(df, period=9)
            
            # 長期トレンドフィルター（長期RCIが+50以上）および RSI過熱のダマシ排除
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
# 4. Gemini API による生成AI分析
# ==========================================
def get_gemini_analysis(matched_stocks):
    # APIキーは環境変数「GEMINI_API_KEY」から自動的に読み込まれます
    try:
        client = genai.Client()
    except Exception as e:
        return f"Geminiクライアントの初期化エラー: {e}。環境変数を確認してください。"

    # 銘柄の有無に応じたプロンプトの出し分け
    if len(matched_stocks) > 0:
        prompt = f"""
        あなたはプロの機関投資家です。本日の株式市場において、以下の銘柄が「出来高を伴う250日新高値ブレイクの初動」としてスクリーニングされました。
        
        【検出銘柄データ】
        {json.dumps(matched_stocks, ensure_ascii=False, indent=2)}
        
        各銘柄について、テクニカル面の数値（RCI、RSI、VWAP乖離、DMI）の強弱を踏まえ、なぜ今このブレイクの初動に乗るべき（あるいは押し目を待つべき）なのか、投資家心理を交えて1銘柄につき3行程度で鋭く論評・解説してください。
        """
    else:
        prompt = """
        あなたはプロの機関投資家です。本日のスクリーニングの結果、東証プライム・スタンダード市場において「出来高を伴う250日新高値ブレイクの条件」を満たす強いモメンタムを持った初動銘柄は「0件」でした。
        
        現在の地合い（押し目形成局面、様子見ムード、資金の逃避など）において、投資家が今どのような心理状態にあり、なぜ無理にエントリーすべきではないのか、「テス流・ハイブリッド投資戦略（RCI等の組み合わせ）」の視点を取り入れた含蓄のある相場解説・アドバイスを、Discordのユーザーに向けて3〜4行で記述してください。
        """

    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=800
            )
        )
        return response.text
    except Exception as e:
        return f"Gemini APIによる解析中にエラーが発生しました: {e}"

# ==========================================
# 5. Discord Webhook へのメッセージ送信
# ==========================================
def send_to_discord(webhook_url, matched_stocks, ai_commentary):
    current_date = datetime.date.today().strftime("%Y年%m%d日")
    
    if len(matched_stocks) > 0:
        embed_fields = []
        for s in matched_stocks:
            value_text = (
                f"**終値**: {s['close']}円\n"
                f"**出来高急増**: 過去平均の `{s['vol_ratio']}倍` 🔥\n"
                f"**新高値まで**: {s['distance_high']}%\n"
                f"**RCI (9/27)**: `{s['rci9']}` / `{s['rci27']}`\n"
                f"**RSI / DMI**: RSI:{s['rsi14']} / {s['dmi_signal']}\n"
                f"**25日VWAP乖離**: {s['vwap_gap']}%"
            )
            embed_fields.append({
                "name": f"📌 {s['name']} ({s['ticker']}) [{s['market']}]",
                "value": value_text,
                "inline": False
            })
            
        payload = {
            "content": f"📡 **【新高値ブレイク初動アラート】** ({current_date} 大引けスキャン)",
            "embeds": [
                {
                    "title": "🎯 条件合致銘柄リスト",
                    "color": 15158332,  # 赤色
                    "fields": embed_fields
                },
                {
                    "title": "💡 【Gemini's Eye】 AI銘柄深掘り解説",
                    "description": ai_commentary,
                    "color": 3447003  # 青色
                }
            ]
        }
    else:
        # 該当銘柄が0件の場合のメッセージ
        payload = {
            "content": f"📡 **【新高値ブレイク自動スクリーニング】** ({current_date})",
            "embeds": [
                {
                    "title": "❌ 本日の該当銘柄は「0件」です",
                    "description": "システムは正常に稼働しましたが、出来高を伴う明確な新高値突破の初動シグナルを検出した銘柄はありませんでした。",
                    "color": 9807270,  # 灰色
                },
                {
                    "title": "📊 【Gemini's Eye】 本日の相場概況アドバイス",
                    "description": ai_commentary,
                    "color": 3447003  # 青色
                }
            ]
        }

    headers = {"Content-Type": "application/json"}
    res = requests.post(webhook_url, data=json.dumps(payload), headers=headers)
    if res.status_code == 204:
        print("Discordへの通知が正常に完了しました。")
    else:
        print(f"Discord通知に失敗しました: {res.status_code}, {res.text}")

# ==========================================
# メイン実行処理
# ==========================================
if __name__ == "__main__":
    DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
    
    if not DISCORD_WEBHOOK_URL:
        print("エラー: DISCORD_WEBHOOK_URL が設定されていません。")
        sys.exit(1)
        
    print("=== スクリプト実行開始 ===")
    
    matched_results = scan_markets()
    print(f"スクリーニング完了。該当件数: {len(matched_results)}件")
    
    ai_analysis = get_gemini_analysis(matched_results)
    send_to_discord(DISCORD_WEBHOOK_URL, matched_results, ai_analysis)
    
    print("=== スクリプト処理終了 ===")
