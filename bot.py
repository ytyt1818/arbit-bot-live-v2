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

# --- הגדרות ניטור (Logging) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# --- שרת Flask ליציבות (Keep-Alive) ---
app = Flask('')
@app.route('/')
def home(): return f"Bot Active | IST: {time.ctime(time.time() + 7200)}"

def run_web():
    port = int(re.sub(r'\D', '', os.environ.get('PORT', '10000')))
    app.run(host='0.0.0.0', port=port)

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
        creds_json = json.loads(creds_raw)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        return gspread.authorize(creds).open(SHEET_NAME)
    except Exception as e:
        logger.error(f"Sheet Auth Error: {e}")
        return None

state = {"last_settings": {}, "last_keep_alive": 0}

def master_cycle():
    global state
    doc = get_sheet_safe()
    if not doc: return 

    try:
        s_sheet = doc.worksheet("Settings")
        p_sheet = doc.worksheet("pairs")
        
        # קריאת נתונים אופטימלית
        rows = s_sheet.get_all_values()
        if len(rows) < 6: return 
        
        current = {
            "target_profit": rows[4][1], # B5
            "keep_alive_interval": rows[5][1], # B6
            "exchanges": sorted(list(set([ex.strip().lower() for ex in s_sheet.col_values(3)[1:] if ex.strip()]))),
            "pairs": sorted(list(set([p.strip().upper() for p in p_sheet.col_values(1)[1:] if p.strip()])))
        }

        # דיווח שינויים "השתנה מ... ל..."
        if state["last_settings"] and current["target_profit"]:
            changes = []
            ls = state["last_settings"]
            
            if str(current["target_profit"]) != str(ls.get("target_profit")):
                changes.append(f"📈 אחוז רווח: השתנה מ-`{ls.get('target_profit')}%` ל-`{current['target_profit']}%` ")
            
            if str(current["keep_alive_interval"]) != str(ls.get("keep_alive_interval")):
                changes.append(f"📢 תדירות דיווח: השתנה מ-`{ls.get('keep_alive_interval')} דק'` ל-`{current['keep_alive_interval']} דק'` ")

            if current['exchanges'] != ls.get('exchanges'):
                added = set(current['exchanges']) - set(ls.get('exchanges', []))
                removed = set(ls.get('exchanges', [])) - set(current['exchanges'])
                if added: changes.append(f"🏦 בורסות שנוספו: `{', '.join(added)}`")
                if removed: changes.append(f"🏦 בורסות שהוסרו: `{', '.join(removed)}`")

            if current['pairs'] != ls.get('pairs'):
                added_p = set(current['pairs']) - set(ls.get('pairs', []))
                removed_p = set(ls.get('pairs', [])) - set(current['pairs'])
                if added_p: changes.append(f"🪙 מטבעות שנוספו: `{', '.join(added_p)}`")
                if removed_p: changes.append(f"🪙 מטבעות שהוסרו: `{', '.join(removed_p)}`")

            if changes:
                bot.send_message(CHAT_ID, "⚙️ **עדכון מערכת בוצע:**\n\n" + "\n".join(changes))

        state["last_settings"] = current
        
        # דיווח סטטוס תקופתי
        ka_val = int(float(current['keep_alive_interval']))
        if (time.time() - state["last_keep_alive"]) >= (ka_val * 60):
            bot.send_message(CHAT_ID, f"🔄 **סטטוס:** סורק {len(current['pairs'])} מטבעות ב-{len(current['exchanges'])} בורסות.")
            state["last_keep_alive"] = time.time()

    except Exception as e: logger.error(f"Cycle Error: {e}")

# --- פקודות טלגרם ---

@bot.message_handler(commands=['add_exchange'])
def add_exchange(message):
    try:
        new_ex = message.text.split()[1].lower()
        if new_ex not in ccxt.exchanges:
            return bot.reply_to(message, f"❌ שגיאה: הבורסה `{new_ex}` לא נתמכת.")
        get_sheet_safe().worksheet("Settings").append_row(["", "", new_ex], table_range="C1")
        bot.reply_to(message, f"⏳ מוסיף את `{new_ex}`... המערכת תתעדכן בקרוב.")
        time.sleep(2)
        master_cycle()
    except: bot.reply_to(message, "ℹ️ שימוש: `/add_exchange binance` ")

@bot.message_handler(commands=['add_pair'])
def add_pair(message):
    try:
        new_p = message.text.split()[1].upper()
        get_sheet_safe().worksheet("pairs").append_row([new_p])
        bot.reply_to(message, f"⏳ מוסיף את `{new_p}` לרשימת המעקב...")
        time.sleep(2)
        master_cycle()
    except: bot.reply_to(message, "ℹ️ שימוש: `/add_pair BTC/USDT` ")

@bot.message_handler(commands=['set_profit'])
def set_profit(message):
    try:
        val = message.text.split()[1]
        get_sheet_safe().worksheet("Settings").update_acell('B5', val)
        bot.reply_to(message, f"⏳ מעדכן רווח יעד ל-`{val}%`...")
        time.sleep(2)
        master_cycle()
    except: bot.reply_to(message, "ℹ️ שימוש: `/set_profit 0.5` ")

@bot.message_handler(commands=['set_report'])
def set_report(message):
    try:
        val = message.text.split()[1]
        get_sheet_safe().worksheet("Settings").update_acell('B6', val)
        bot.reply_to(message, f"⏳ מעדכן תדר דיווח ל-`{val}` דקות...")
        time.sleep(2)
        master_cycle()
    except: bot.reply_to(message, "ℹ️ שימוש: `/set_report 15` ")

@bot.message_handler(commands=['status'])
def cmd_status(message):
    if state["last_settings"]:
        ls = state["last_settings"]
        msg = (f"⚙️ **מצב נוכחי:**\n"
               f"📈 רווח יעד: `{ls['target_profit']}%` \n"
               f"📢 דיווח: כל `{ls['keep_alive_interval']} דק'` \n"
               f"🏦 בורסות: `{', '.join(ls['exchanges'])}` \n"
               f"🪙 מטבעות: `{len(ls['pairs'])}` פעילים.")
        bot.reply_to(message, msg)

@bot.message_handler(commands=['start', 'help'])
def cmd_help(message):
    help_text = "🤖 **תפריט שליטה:**\n/status | /check | /set_profit | /set_report | /add_exchange | /add_pair"
    bot.reply_to(message, help_text)

if __name__ == "__main__":
    master_cycle()
    scheduler = BackgroundScheduler()
    scheduler.add_job(master_cycle, 'interval', seconds=60)
    scheduler.start()
    while True:
        try: bot.polling(none_stop=True, timeout=40)
        except: time.sleep(10)
