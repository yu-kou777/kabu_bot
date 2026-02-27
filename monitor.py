# monitor.py の一部
def check_1m_logic(item):
    # ...略...
    df['MA60'] = df['Close'].rolling(60).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    
    # ✅ 20分前のMAの値と現在のMAの値を比較（タイムラグ修正・トレンド予測）
    # 差分（diff）がプラス同士、またはマイナス同士なら「同じ方向を向いている」と判定
    is_strong = (df['MA60'].diff(20).iloc[-1] * df['MA200'].diff(20).iloc[-1] > 0)
    
    last = df.iloc[-1]; sigs = []
    # 友幸さんの黄金法則判定
    if last['Close'] > ma60.iloc[-1]:
        if (df['High'].tail(10) >= bb_u2.tail(10)).sum() >= 3: sigs.append("法則1:BB+2σx3(売)")
    # ...略...
    
    for s in sigs:
        # トレンドが確定していれば「💎」を付ける
        label = "💎【超王道・20分確定】" if is_strong else "🔔"
        send_discord(f"{label} **【{reason}】{ticker}**\n{s}")
