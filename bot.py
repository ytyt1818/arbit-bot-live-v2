import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import telebot
import ccxt
import json
from flask import Flask
from threading import Thread
from apscheduler.schedulers.background import BackgroundScheduler

# --- שרת דמה ליציבות ב-Render ---
app = Flask('')
@app.route('/')
def home(): return "Arbit-Bot Control Panel is Online"
def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
Thread(target=run_web).start()

# --- הגדרות בוט ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
SHEET_NAME = "arbit-bot-live_Control_Panel"
bot = telebot.TeleBot(TOKEN)

def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = json.loads(os.environ.get('GSPREAD_CREDENTIALS'))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    return gspread.authorize(creds).open(SHEET_NAME)

last_settings = {}
last_keep_alive_time = 0

def run_logic():
    global last_settings, last_keep_alive_time
    try:
        doc = get_sheet()
        settings_sheet = doc.worksheet("Settings")
        pairs_sheet = doc.worksheet("pairs")
        
        # 1. קריאת כל הפרמטרים מהאקסל
        current = {
            "interval": int(settings_sheet.acell('B3').value),
            "profit": float(settings_sheet.acell('B5').value),
            "keep_alive": int(settings_sheet.acell('B6').value),
            "exchanges": [ex.strip().lower() for ex in settings_sheet.col_values(3)[1:] if ex.strip()],
            "pairs": [p.strip().upper() for p in pairs_sheet.col_values(1)[1:] if p.strip()]
        }

        # 2. זיהוי שינויים ושליחת עדכון לטלגרם
        if last_settings and (current != last_settings):
            msg = "⚙️ **הגדרות עודכנו מהאקסל!**\n"
            if current['profit'] != last_settings.get('profit'):
                msg += f"📈 רווח יעד: {current['profit']}%\n"
            if current['exchanges'] != last_settings.get('exchanges'):
                msg += f"🏦 בורסות: {', '.join(current['exchanges'])}\n"
            if current['pairs'] != last_settings.get('pairs'):
                msg += f"🪙 מספר צמדים: {len(current['pairs'])}\n"
            bot.send_message(CHAT_ID, msg)
        
        last_settings = current

        # 3. בדיקת זמן דיווח תקופתי
        current_time = time.time()
        if current_time - last_keep_alive_time >= (current['keep_alive'] * 60):
            bot.send_message(CHAT_ID, f"🔄 דיווח תקופתי: סורק {len(current['pairs'])} צמדים ב-{len(current['exchanges'])} בורסות.")
            last_keep_alive_time = current_time

        # 4. ביצוע סריקת ארביטראז' לפי הרשימה המעודכנת
        active_exchanges = {}
        for ex_name in current['exchanges']:
            if hasattr(ccxt, ex_name):
                active_exchanges[ex_name] = getattr(ccxt, ex_name)()

        for pair in current['pairs']:
            prices = {}
            for name, ex in active_exchanges.items():
                try:
                    ticker = ex.fetch_ticker(pair)
                    prices[name] = ticker['last']
                except: continue
            
            if len(prices) > 1:
                low_ex = min(prices, key=prices.get)
                high_ex = max(prices, key=prices.get)
                diff = ((prices[high_ex] - prices[low_ex]) / prices[low_ex]) * 100
                
                if diff >= current['profit']:
                    alert = f"💰 **הזדמנות!** {pair}\n📉 קנייה ({low_ex}): {prices[low_ex]}\n📈 מכירה ({high_ex}): {prices[high_ex]}\n📊 פער: {diff:.2f}%"
                    bot.send_message(CHAT_ID, alert)

    except Exception as e:
        print(f"Error in main loop: {e}")

# הפעלה כל 60 שניות (בודק אקסל + מבצע סריקה)
scheduler = BackgroundScheduler()
scheduler.add_job(run_logic, 'interval', seconds=60)
scheduler.start()

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🚀 הבוט הופעל! מעכשיו הוא עוקב אחרי כל שינוי באקסל (בורסות, מטבעות והגדרות).")
    while True: time.sleep(1)
