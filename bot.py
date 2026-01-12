import ccxt
import time
import requests
import threading
from flask import Flask
import os

# שרת לבדיקת תקינות (Health Check)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running securely!", 200

def run_flask():
    # שימוש בפורט 10000 כברירת מחדל של Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# משיכת הנתונים המאובטחים שהגדרת ב-Render
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
    'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'MATIC/USDT', 'LINK/USDT',
    'DOGE/USDT', 'SHIB/USDT', 'LTC/USDT', 'BCH/USDT', 'UNI/USDT',
    'NEAR/USDT', 'TIA/USDT', 'APT/USDT', 'OP/USDT', 'ARB/USDT'
]

exchanges = {
    'bybit': ccxt.bybit(),
    'mexc': ccxt.mexc({'options': {'adjustForTimeDifference': True}}),
    'okx': ccxt.okx()
}

def send_telegram_message(message):
    if not TOKEN or not CHAT_ID:
        print("Error: Missing TOKEN or CHAT_ID in Environment variables!")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, json=payload)
        print(f"Telegram status: {response.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

def check_arbitrage():
    print("Starting secure scanner loop...")
    send_telegram_message("✅ הבוט הופעל בהצלחה במצב מאובטח! מתחיל סריקה...")
    
    while True:
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
                avg_fees = 0.2
                net_diff = diff - avg_fees

                if net_diff > 0.05:
                    msg = (f"🔍 נמצא פער (בדיקה): {symbol}\n"
                           f"קנה ב-{lowest}: {prices[lowest]}\n"
                           f"מכור ב-{highest}: {prices[highest]}\n"
                           f"רווח נטו: {net_diff:.2f}%")
                    send_telegram_message(msg)
        
        time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    check_arbitrage()
