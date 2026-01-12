import ccxt
import time
import requests
import threading
from flask import Flask
import os
from datetime import datetime

app = Flask(__name__)

# פונקציה להפקת זמן נוכחי (לפי בקשתך הקבועה)
def get_current_time():
    return datetime.now().strftime("%H:%M:%S")

@app.route('/')
def home():
    return f"Bot is running. Current Server Time: {get_current_time()}", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# משיכת המשתנים מה-Environment של Render
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
    'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT', 'LINK/USDT'
]

exchanges = {
    'bybit': ccxt.bybit(),
    'mexc': ccxt.mexc({'options': {'adjustForTimeDifference': True}}),
    'okx': ccxt.okx()
}

def send_telegram_message(message):
    if not TOKEN or not CHAT_ID:
        print(f"[{get_current_time()}] ❌ שגיאה: המשתנים TELEGRAM_TOKEN או CHAT_ID לא הוגדרו ב-Render")
        return
    
    # הוספת השעה לגוף ההודעה בטלגרם
    full_message = f"[{get_current_time()}] {message}"
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": full_message}
    try:
        response = requests.post(url, json=payload, timeout=10)
        # הדפסת סטטוס ליומנים לצורך בקרה
        print(f"[{get_current_time()}] 📡 סטטוס שליחה לטלגרם: {response.status_code}")
    except Exception as e:
        print(f"[{get_current_time()}] ❌ שגיאת תקשורת עם טלגרם: {e}")

def check_arbitrage():
    # הדפסה ליומנים של Render
    print(f"[{get_current_time()}] 🚀 הבוט הופעל בהצלחה ומתחיל סריקה")
    
    # שליחת הודעה מיידית לטלגרם עם העלייה (כדי לוודא שהטוקן תקין)
    send_telegram_message("✅ הבוט עלה לאוויר! מעתה תקבל דיווח כל חצי שעה והתראות על פערים.")
    
    last_heartbeat = time.time()
    
    while True:
        # שליחת הודעת "אני חי" כל 30 דקות (1800 שניות)
        if time.time() - last_heartbeat >= 1800:
            send_telegram_message("🔄 דיווח חצי-שעתי: הבוט סורק ומחפש פערים.")
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
                highest = max(prices, key=prices.get)
                lowest = min(prices, key=prices.get)
                diff = ((prices[highest] - prices[lowest]) / prices[lowest]) * 100
                net_diff = diff - 0.2 # הפחתת עמלות משוערת

                if net_diff > 0.05:
                    msg = (f"💰 פער נמצא!\n"
                           f"מטבע: {symbol}\n"
                           f"קנה ב-{lowest}: {prices[lowest]}\n"
                           f"מכור ב-{highest}: {prices[highest]}\n"
                           f"רווח נטו מוערך: {net_diff:.2f}%")
                    send_telegram_message(msg)
        
        time.sleep(30)

if __name__ == "__main__":
    # הרצת שרת ה-Flask ברקע כדי ש-Render לא יכבה את הבוט
    threading.Thread(target=run_flask, daemon=True).start()
    # הרצת סורק הארביטראז'
    check_arbitrage()
