# monitor.py の修正ポイント
AUTO_LIST_FILE = "auto_scan_list.json"

# --- 15時のスキャン処理 ---
def afternoon_auto_scan():
    # ...（スキャン実行）...
    # 見つかった銘柄を auto_scan_list.json に保存
    with open(AUTO_LIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_watchlist, f, ensure_ascii=False, indent=2)
    # Discordへ通知
    send_discord("🕒 AIが明日狙うべき銘柄を自動リストアップしました。ストリームリットで確認できます。")

# --- 1分足の監視処理 ---
def monitor_all():
    # 手動リストと自動リストの両方を読み込んでループ
    target_files = [WATCHLIST_FILE, AUTO_LIST_FILE]
    for file_path in target_files:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                watchlist = json.load(f)
                for item in watchlist:
                    check_logic_1m(item) # 法則8を含む8つの黄金法則で判定
