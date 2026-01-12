import ccxt
import time
import requests
import threading
from flask import Flask
import os
from datetime import datetime

app = Flask(__name__)

# פונקציה להצגת שעה בפורמט HH:MM:SS
def get_current_time():
    return datetime.now().strftime("%H:%M:%S")

@app.route('/')
def home():
    return f"Bot is running. Server Time: {get_current_time()}", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# משיכת המשתנים מה-Environment (הגדרות Render)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

def send_telegram_message(message):
    print(f"[{get_current_time()}] 🔍 מנסה לשלוח הודעה ל-CHAT_ID: {CHAT_ID}")
    
    if not TOKEN or not CHAT_ID:
        print(f"[{get_current_time()}] ❌ שגיאה קריטית: TOKEN או CHAT_ID חסרים ב-Render!")
        return
    
    timed_msg = f"[{get_current_time()}] {message}"
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": timed_msg}
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        # זהו הדיווח החשוב ביותר ביומנים (Logs)
        print(f"[{get_current_time()}] 📡 תשובת טלגרם: {response.status_code}")
        if response.status_code != 200:
            print(f"[{get_current_time()}] ⚠️ טלגרם סירב לבקשה. סיבה: {response.text}")
    except Exception as e:
        print(f"[{get_current_time()}] ❌ שגיאת תקשורת חמורה: {e}")

def check_arbitrage():
    # הודעה ראשונה שחייבת להופיע ב-Logs (image_e6e3d0.png)
    print(f"[{get_current_time()}] 🚀 הבוט התניע גרסה חדשה ומתחיל סריקה")
    
    # שליחת הודעה מיידית - המבחן הסופי
    send_telegram_message("✅ בדיקת מערכת: הבוט מחובר לטלגרם ומתחיל לסרוק פערים.")
    
    SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT', 'LINK/USDT']
    exchanges = {
        'bybit': ccxt.bybit(),
        'mexc': ccxt.mexc({'options': {'adjustForTimeDifference': True}}),
        'okx': ccxt.okx()
    }
    
    last_heartbeat = time.time()
    
    while True:
        # דיווח "דופק" כל 30 דקות
        if time.time() - last_heartbeat >= 1800:
            send_telegram_message("🔄 דיווח תקופתי: הבוט סורק ומחפש פערים.")
            last_heartbeat = time.time()

        for symbol in SYMBOLS:
            prices = {}
            for name, exchange in exchanges.items():
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    prices[name] = ticker['last']
                except:
                    continue

            if len(prices) > 1:
                hi, lo = max(prices, key=prices.get), min(prices, key=prices.get)
                diff = ((prices[hi] - prices[lo]) / prices[lo]) * 100
                net_diff = diff - 0.2

                if net_diff > 0.05:
                    send_telegram_message(f"💰 פער ב-{symbol}: קנה ב-{lo}, מכור ב-{hi}. רווח נטו: {net_diff:.2f}%")
        
        time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    check_arbitrage()
