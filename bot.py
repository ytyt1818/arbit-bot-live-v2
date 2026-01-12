import ccxt
import time
import requests
import threading
from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Live and Secure", 200

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
    # בדיקה אם המשתנים קיימים בזיכרון של השרת
    if not TOKEN or not CHAT_ID:
        print(f"DEBUG: Credentials missing! TOKEN: {bool(TOKEN)}, CHAT: {bool(CHAT_ID)}")
        return
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Telegram status: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Telegram connection error: {e}")

def check_arbitrage():
    # שורה זו חייבת להופיע ב-Logs כדי לדעת שהקוד רץ
    print("🚀 Scanner started successfully")
    
    # ניסיון שליחה ראשון מיד עם העלייה
    send_telegram_message("⚡️ הבוט חזר לפעילות! מתחיל סריקה מאובטחת.")
    
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
                net_diff = diff - 0.2

                if net_diff > 0.05:
                    msg = (f"💰 פער נמצא!\n"
                           f"מטבע: {symbol}\n"
                           f"קנה ב-{lowest}: {prices[lowest]}\n"
                           f"מכור ב-{highest}: {prices[highest]}\n"
                           f"רווח נטו: {net_diff:.2f}%")
                    send_telegram_message(msg)
        
        time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    check_arbitrage()
