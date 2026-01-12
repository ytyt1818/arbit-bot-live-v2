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

# משיכת נתונים מ-Render Environment
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT', 'LINK/USDT']

exchanges = {
    'bybit': ccxt.bybit(),
    'mexc': ccxt.mexc({'options': {'adjustForTimeDifference': True}}),
    'okx': ccxt.okx()
}

def send_telegram_message(message):
    if not TOKEN or not CHAT_ID:
        print(f"[{get_current_time()}] ❌ שגיאה: TOKEN או CHAT_ID חסרים ב-Render Environment")
        return
    
    timed_msg = f"[{get_current_time()}] {message}"
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": timed_msg}
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        # השורה הזו חייבת להופיע בלוגים אם הקוד רץ!
        print(f"[{get_current_time()}] 📡 ניסיון שליחה לטלגרם - סטטוס: {response.status_code}")
    except Exception as e:
        print(f"[{get_current_time()}] ❌ שגיאת חיבור לטלגרם: {e}")

def check_arbitrage():
    # הודעה ראשונה שחייבת להופיע ב-Logs של Render
    print(f"[{get_current_time()}] 🚀 הבוט התניע ומתחיל סריקה")
    
    # הודעה מיידית לטלגרם כדי שתדע שזה עובד
    send_telegram_message("✅ הבוט עלה לאוויר! תקבל דיווח בכל חצי שעה ובכל זיהוי רווח.")
    
    last_heartbeat = time.time()
    
    while True:
        # דיווח חצי שעתי (1800 שניות)
        if time.time() - last_heartbeat >= 1800:
            send_telegram_message("🔄 דיווח חצי-שעתי: הבוט פעיל וסורק.")
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
                hi = max(prices, key=prices.get)
                lo = min(prices, key=prices.get)
                diff = ((prices[hi] - prices[lo]) / prices[lo]) * 100
                net_diff = diff - 0.2

                if net_diff > 0.05:
                    msg = (f"💰 פער נמצא!\n"
                           f"מטבע: {symbol}\n"
                           f"קנה ב-{lo}: {prices[lo]}\n"
                           f"מכור ב-{hi}: {prices[hi]}\n"
                           f"רווח נטו: {net_diff:.2f}%")
                    send_telegram_message(msg)
        
        time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    check_arbitrage()
