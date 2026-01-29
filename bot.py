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

# --- ניטור מערכת (Logging) ---
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
    return f"Bot Status: ACTIVE | IST Time: {time.ctime(time.time() + 7200)}"

def run_web():
    port_env = os.environ.get('PORT', '10000')
    clean_port = int(re.sub(r'\D', '', port_env))
    app.run(host='0.0.0.0', port=clean_port)

Thread(target=run_web, daemon=True).start()

# --- הגדרות ליבה ---
TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
SHEET_NAME = "arbit-bot-live_Control_Panel"
bot = telebot.TeleBot(TOKEN, parse_mode='Markdown')

def get_sheet_safe():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_raw = os.environ.get('GSPREAD_CREDENTIALS', '').strip()
        if not creds_raw: return None
        if not creds_raw.startswith('{'):
            creds_raw = creds_raw[creds_raw.find('{'):creds_raw.rfind('}')+1]
        creds_json = json.loads(creds_raw)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        return gspread.authorize(creds).open(SHEET_NAME)
    except Exception as e:
        logger.error(f"Auth Error: {e}")
        return None

state = {"last_settings": {}, "last_keep_alive": 0}

def master_cycle():
    global state
    logger.info("--- Starting Master Cycle ---")
    doc = get_sheet_safe()
    if not doc: return 

    try:
        s_sheet = doc.worksheet("Settings")
        p_sheet = doc.worksheet("pairs")
        
        current = {
            "keep_alive_minutes": s_sheet.acell('B2').value or "0",
            "scan_interval": s_sheet.acell('B3').value or "60",
            "target_volume": s_sheet.acell('B4').value or "0",
            "target_profit": s_sheet.acell('B5').value or "0.5",
            "keep_alive_interval": s_sheet.acell('B6').value or "60",
            "exchanges": sorted([ex.strip().lower() for ex in s_sheet.col_values(3)[1:] if ex.strip()]),
            "pairs": sorted([p.strip().upper() for p in p_sheet.col_values(1)[1:] if p.strip()])
        }

        # דיווח שינויים מפורט (היה ➔ השתנה)
        if state["last_settings"]:
            changes = []
            ls = state["last_settings"]
            mapping = {"target_profit": "📈 רווח", "scan_interval": "⏱ סריקה", "keep_alive_interval": "📢 דיווח"}
            
            for key, label in mapping.items():
                if str(current[key]) != str(ls.get(key)):
                    changes.append(f"{label}: `{ls.get(key)}` ➔ `{current[key]}`")
            
            if current['exchanges'] != ls.get('exchanges'):
                added = set(current['exchanges']) - set(ls.get('exchanges', []))
                removed = set(ls.get('exchanges', [])) - set(current['exchanges'])
                if added: changes.append(f"🏦 נוספו בורסות: `{', '.join(added)}`")
                if removed: changes.append(f"🏦 הוסרו בורסות: `{', '.join(removed)}`")

            if current['pairs'] != ls.get('pairs'):
                added_p = set(current['pairs']) - set(ls.get('pairs', []))
                removed_p = set(ls.get('pairs', [])) - set(current['pairs'])
                if added_p: changes.append(f"🪙 נוספו מטבעות: `{', '.join(added_p)}`")
                if removed_p: changes.append(f"🪙 הוסרו מטבעות: `{', '.join(removed_p)}`")

            if changes:
                bot.send_message(CHAT_ID, "⚙️ **שינוי בהגדרות זוהה:**\n\n" + "\n".join(changes))

        state["last_settings"] = current

        # סריקת ארביטראז'
        profit_val = float(current['target_profit'])
        active_ex = {name: getattr(ccxt, name)() for name in current['exchanges'] if hasattr(ccxt, name)}
        for pair in current['pairs']:
            prices = {}
            for name, ex in active_ex.items():
                try: prices[name] = ex.fetch_ticker(pair)['last']
                except: continue
            if len(prices) > 1:
                low_ex, high_ex = min(prices, key=prices.get), max(prices, key=prices.get)
                diff = ((prices[high_ex] - prices[low_ex]) / prices[low_ex]) * 100
                if diff >= profit_val:
                    bot.send_message(CHAT_ID, f"💰 **הזדמנות!** *{pair}*\n📊 פער: `{diff:.2f}%` \n{low_ex} ➔ {high_ex}")

        if (time.time() - state["last_keep_alive"]) >= (int(float(current['keep_alive_interval'])) * 60):
            bot.send_message(CHAT_ID, f"🔄 **סטטוס:** סורק {len(current['pairs'])} מטבעות ב-{len(current['exchanges'])} בורסות.")
            state["last_keep_alive"] = time.time()
    except Exception as e:
        logger.error(f"Cycle Error: {e}")

# --- ממשק פקודות טלגרם עם הנחיות (User Experience) ---

@bot.message_handler(commands=['start', 'help'])
def cmd_help(message):
    help_text = (
        "🤖 **מדריך פקודות Arbit-Bot:**\n\n"
        "📊 `/status` - צפייה בהגדרות הנוכחיות.\n"
        "🔍 `/check` - הרצת סריקה ידנית עכשיו.\n"
        "📈 `/set_profit` - שינוי אחוז רווח יעד.\n"
        "📢 `/set_report` - שינוי תדירות דיווח (בדקות).\n"
        "🏦 `/add_exchange` - הוספת בורסה חדשה.\n"
        "🪙 `/add_pair` - הוספת צמד מטבעות למעקב.\n\n"
        "💡 *רוצה לדעת איך להשתמש בפקודה? שלח רק את שם הפקודה (למשל `/add_exchange`) ותקבל הסבר.*"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['add_exchange'])
def add_exchange(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "ℹ️ **איך להוסיף בורסה?**\nרשום את הפקודה ואחריה את שם הבורסה באנגלית.\n\nדוגמה: `/add_exchange binance` או `/add_exchange kraken` ")
    try:
        new_ex = args[1].lower()
        doc = get_sheet_safe()
        s_sheet = doc.worksheet("Settings")
        s_sheet.append_row(["", "", new_ex], table_range="C1")
        bot.reply_to(message, f"✅ הבורסה `{new_ex}` נוספה לאקסל. הבוט יתחיל לסרוק אותה בסבב הבא.")
    except Exception as e: bot.reply_to(message, f"⚠️ שגיאה בעדכון: {e}")

@bot.message_handler(commands=['add_pair'])
def add_pair(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "ℹ️ **איך להוסיף צמד מטבעות?**\nרשום את הפקודה ואחריה את הצמד באותיות גדולות עם לוכסן.\n\nדוגמה: `/add_pair BTC/USDT` או `/add_pair ETH/USDC` ")
    try:
        new_p = args[1].upper()
        doc = get_sheet_safe()
        p_sheet = doc.worksheet("pairs")
        p_sheet.append_row([new_p])
        bot.reply_to(message, f"✅ הצמד `{new_p}` נוסף לרשימת המעקב באקסל.")
    except Exception as e: bot.reply_to(message, f"⚠️ שגיאה בעדכון: {e}")

@bot.message_handler(commands=['set_profit'])
def set_profit(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "ℹ️ **איך לשנות רווח יעד?**\nרשום את הפקודה ואחריה את המספר באחוזים.\n\nדוגמה ל-0.8 אחוז: `/set_profit 0.8` ")
    try:
        new_val = args[1]
        doc = get_sheet_safe()
        doc.worksheet("Settings").update('B5', new_val)
        bot.reply_to(message, f"✅ רווח יעד עודכן ל-`{new_val}%` ")
    except Exception as e: bot.reply_to(message, f"⚠️ שגיאה: {e}")

@bot.message_handler(commands=['set_report'])
def set_report(message):
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "ℹ️ **איך לשנות תדירות דיווח?**\nרשום את הפקודה ואחריה את מספר הדקות לדיווח.\n\nדוגמה לדיווח כל שעה: `/set_report 60` ")
    try:
        new_val = args[1]
        doc = get_sheet_safe()
        doc.worksheet("Settings").update('B6', new_val)
        bot.reply_to(message, f"✅ תדירות דיווח עודכנה ל-`{new_val}` דקות.")
    except Exception as e: bot.reply_to(message, f"⚠️ שגיאה: {e}")

@bot.message_handler(commands=['status'])
def cmd_status(message):
    if state["last_settings"]:
        ls = state["last_settings"]
        msg = (f"⚙️ **מצב מערכת נוכחי:**\n\n"
               f"📈 רווח יעד: `{ls['target_profit']}%` \n"
               f"📢 דיווח כל: `{ls['keep_alive_interval']} דק'` \n"
               f"🏦 בורסות: `{', '.join(ls['exchanges'])}` \n"
               f"🪙 מטבעות: `{len(ls['pairs'])}` פעילים.")
        bot.reply_to(message, msg)

@bot.message_handler(commands=['check'])
def manual_check(message):
    bot.send_message(message.chat.id, "🔎 מבצע סריקה ידנית לבקשתך...")
    master_cycle()

if __name__ == "__main__":
    master_cycle()
    scheduler = BackgroundScheduler()
    scheduler.add_job(master_cycle, 'interval', seconds=60)
    scheduler.start()
    while True:
        try: bot.polling(none_stop=True, timeout=40)
        except Exception as e: time.sleep(10)
