# --- 📡 1. 朝の日足全件スキャン（修正版） ---
def run_daily_scan():
    print(f"🚀 プライム市場全件スキャン開始: {get_jst_now()}")
    
    # 💡 本来は全1600件のリストをここに入れます（長いため主要な拡張版を例示）
    # 実際にはJPXの公式サイトから全コードを取得するロジックを組むのが理想です
    ALL_PRIME_TICKERS = [f"{i}.T" for i in range(1000, 9999)] # 1000番台〜9000番台を全チェック
    
    hits = {}
    chunk_size = 400 # 400銘柄ずつに分ける
    
    for i in range(0, len(ALL_PRIME_TICKERS), chunk_size):
        batch = ALL_PRIME_TICKERS[i : i + chunk_size]
        print(f"📦 バッチ {i//chunk_size + 1} 実行中... ({len(batch)}銘柄)")
        
        try:
            # 最新のデータ（RSI/RCI判定用）を取得
            data = yf.download(batch, period="1y", progress=False)['Close']
            
            for t in batch:
                if t not in data or data[t].isnull().all(): continue
                c = data[t].dropna()
                if len(c) < 30: continue
                
                # RSIとRCIを計算
                rsi = calculate_rsi(c, 14).iloc[-1]
                rci = calculate_rci(c, 9).iloc[-1]
                
                # ✅ ジャックさんの「お宝条件」で判定
                if (rsi <= 20 and rci <= -70) or (rsi >= 90 and rci >= 95):
                    hits[t] = f"極値(RSI:{rsi:.0f}/RCI:{rci:.0f})"
                    print(f"✨ お宝発見: {t} {hits[t]}")
        
        except Exception as e:
            print(f"⚠️ バッチ実行中にスキップが発生しました")
            continue
            
        time.sleep(5) # サーバーを休ませるための5秒休憩

    # 結果を保存
    with open(PRE_SCAN_FILE, 'w', encoding='utf-8') as f:
        json.dump({"date": get_jst_now().strftime('%Y-%m-%d'), "hits": hits}, f)
    print(f"🏁 全件スキャン完了：{len(hits)}件を抽出しました")
