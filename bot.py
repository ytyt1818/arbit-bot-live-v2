import telebot
import time
import os
import ccxt
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from flask import Flask # פותר את בעיית ה-Port ב-Render

# הגדרת לוגים
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# שרת דמי (Dummy) כדי לספק את Render ולמנוע הודעות Port
app = Flask(__name__)
@app.route('/')
def health_check():
    return "Bot is alive", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = telebot.TeleBot(TOKEN)

# מצב מערכת
state = {
    "is_running": True,
    "profit_threshold": 0.3,
    "symbol": "BTC/USDT",
    "target_chat_id": None, 
    "active_exchanges": ['binance', 'bybit', 'kucoin', 'okx', 'mexc', 'bingx']
}

def get_israel_time():
    return (datetime.utcnow() + timedelta(hours=2)).strftime('%H:%M:%S')

# ---Handlers לפקודות ---

@bot.message_handler(commands=['status'])
def cmd_status(message):
    state["target_chat_id"] = message.chat.id
    msg = (f"📊 *מערכת Arbi-Bot Live*\n"
           f"🕒 זמן ישראל: `{get_israel_time()}`\n"
           f"📈 סף רווח: `{state['profit_threshold']}%`\n"
           f"✅ סטטוס: סורק בורסות במקביל")
    bot.reply_to(message, msg, parse_mode='Markdown')

# --- הפעלה יציבה למניעת Conflict 409 ---
def start_bot():
    while True:
        try:
            logger.info("Cleaning Webhooks to solve Conflict 409...")
            bot.remove_webhook()
            bot.infinity_polling(timeout=25, long_polling_timeout=20)
        except Exception as e:
            logger.error(f"Bot Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    # הפעלת שרת הבריאות עבור Render (פותר את הודעת ה-No open ports)
    threading.Thread(target=run_flask, daemon=True).start()
    
    # הפעלת הבוט
    start_bot()
