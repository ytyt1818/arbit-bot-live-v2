import os
import time
import json
import gspread
import telebot
import ccxt
import re
import logging
import sys
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask
from threading import Thread
from apscheduler.schedulers.background import BackgroundScheduler

# --- הגדרת ניטור מקצועי (Logging) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- שרת Flask ליציבות (Keep-Alive) ---
app = Flask('')
@app.route('/')
def home():
    return f"Bot Status: ACTIVE | System Time: {time.ctime()}"

def run_web():
    try:
        port_env = os.environ.get('PORT', '10000')
        clean_port = int(re.sub(r'\D', '', port_env))
        logger.info(f"Starting Web Server on port {clean_port}")
        app.run(host='0.0.0.0', port=clean_port)
    except Exception as e:
        logger.error(f"Flask Server Error: {e}")

# הרצת השרת ב-Thread נפרד וחסין
web_thread = Thread(target=run_web, daemon=True)
web_thread.start()

# --- הגדרות ליבה וחיבורים ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
SHEET_NAME = "arbit-bot-live_Control_Panel"

# אתחול בוט עם מנגנון Timeout מובנה
bot = telebot.TeleBot(TOKEN, parse_mode='Markdown', threaded=False)

def get_sheet_safe():
    """חיבור בטוח לגוגל שיטס עם מנגנון ניסיונות חוזרים"""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_raw = os.environ.get('GSPREAD_CREDENTIALS')
        if not creds_raw: raise ValueError("Missing GSPREAD_CREDENTIALS")
        creds_json = json.loads(creds_raw)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        return gspread.authorize(creds).open(SHEET_NAME)
    except Exception as e:
        logger.error(f"Google Sheets Connection Failed: {e}")
        return None

last_settings = {}
last_keep_alive_time = 0

def master_cycle():
    """המחזור המרכזי: עדכון הגדרות + סריקת ארביטראז'"""
    global last_settings, last_keep_alive_time
    logger.info("--- Starting Master Cycle ---")
    
    doc = get_sheet_safe()
    if not doc: return # דילוג על הסבב אם אין חיבור לגוגל

    try:
        s_sheet = doc.worksheet("Settings")
        p_sheet = doc.worksheet("pairs")
        
        # משיכת נתונים בטוחה
        current = {
            "interval": int(float(s_sheet.acell('B3').value or 60)),
            "profit": float(s_sheet.acell('B5').value or 0.6),
            "keep_alive": int(float(s_sheet.acell('B6').value or 60)),
            "exchanges": [ex.strip().lower() for ex in s_sheet.col_values(3)[1:] if ex.strip()],
            "pairs": [p.strip().upper() for p in p_sheet.col_values(1)[1:] if p.strip()]
        }

        # דיווח על שינויים בזמן אמת
        if last_settings:
            changes = []
            if current['profit'] != last_settings.get('profit'):
                changes.append(f"📈 רווח יעד: `{last_settings['profit']}%` ➔ `{current['profit']}%` ")
            if set(current['pairs']) != set(last_settings.get('pairs', [])):
                changes.append(f"🪙 רשימת המטבעות עודכנה")
            if changes:
                bot.send_message(CHAT_ID, "⚙️ **עדכון הגדרות זוהה:**\n" + "\n".join(changes))

        last_settings = current

        # ביצוע סריקת ארביטראז'
        active_ex = {name: getattr(ccxt, name)() for name in current['exchanges'] if hasattr(ccxt, name)}
        for pair in current['pairs']:
            prices = {}
            for name, ex in active_ex.items():
                try:
                    ticker = ex.fetch_ticker(pair)
                    prices[name] = ticker['last']
                except: continue
            
            if len(prices) > 1:
                low_ex, high_ex = min(prices, key=prices.get), max(prices, key=prices.get)
                diff = ((prices[high_ex] - prices[low_ex]) / prices[low_ex]) * 100
                if diff >= current['profit']:
                    bot.send_message(CHAT_ID, f"💰 **הזדמנות!** {pair}\n📊 פער: `{diff:.2f}%` \nקנייה: {low_ex} | מכירה: {high_ex}")

        # ניהול Keep-Alive (הודעת סטטוס)
        if (time.time() - last_keep_alive_time) >= (current['keep_alive'] * 60):
            bot.send_message(CHAT_ID, f"🔄 **דיווח בוט:** המערכת פועלת. {len(current['pairs'])} צמדים נסרקים.")
            last_keep_alive_time = time.time()

    except Exception as e:
        logger.error(f"Error in master cycle: {e}")

# --- פקודות טלגרם (UI) ---
@bot.message_handler(commands=['status'])
def cmd_status(message):
    if last_settings:
        msg = f"✅ **בוט מחובר ופעיל**\n📈 רווח יעד: `{last_settings['profit']}%` \n🏦 בורסות: `{len(last_settings['exchanges'])}`"
    else:
        msg = "⚠️ הבוט בטעינה ראשונית..."
    bot.reply_to(message, msg)

# --- הפעלה וניהול תהליכים ---
if __name__ == "__main__":
    # הרצה ראשונית מיידית
    master_cycle()

    # תזמון קבוע וחסין
    scheduler = BackgroundScheduler()
    scheduler.add_job(master_cycle, 'interval', seconds=60, max_instances=1)
    scheduler.start()

    logger.info("Bot Polling Started...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=40)
        except Exception as e:
            logger.error(f"Polling error: {e}. Restarting in 10s...")
            time.sleep(10)
