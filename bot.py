import ccxt
import time
import requests
import threading
from flask import Flask

# הגדרת שרת אינטרנט קטן כדי ש-Render יראה שהבוט "חי"
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!", 200

def run_flask():
    # Render מעבירה את הפורט במשתנה סביבה, אם לא קיים נשתמש ב-8080
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- הגדרות הבוט שלך ---
TOKEN = "7369970928:AAHny6v0fN7V_hWlT7L3z67S8zI-yY3D7oY"
CHAT_ID = "5334659223"

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
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def check_arbitrage():
    send_telegram_message("🤖 הבוט המעודכן הופעל בהצלחה בשרת הענן!")
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
                net_diff = diff - 0.2  # הערכת עמלות

                if net_diff > 0.25:
                    msg = (f"🚀 הזדמנות ארביטראז'!\nנכס: {symbol}\n"
                           f"קנה ב-{lowest}: {prices[lowest]}\n"
                           f"מכור ב-{highest}: {prices[highest]}\n"
                           f"רווח נטו מוערך: {net_diff:.2f}%")
                    send_telegram_message(msg)
        
        print("No open ports detected, continuing to scan...") # הודעה ללוגים של Render
        time.sleep(30)

if __name__ == "__main__":
    # הפעלת שרת האינטרנט בשרשור נפרד (Thread) כדי שלא יעצור את הבוט
    threading.Thread(target=run_flask).start()
    # הפעלת סורק הארביטראז'
    check_arbitrage()
