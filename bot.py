import os
import time
import json
import gspread
import telebot
from telebot import types
import ccxt
import re
import logging
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask
from threading import Thread
from apscheduler.schedulers.background import BackgroundScheduler
from concurrent.futures import ThreadPoolExecutor # לעיבוד מקבילי מהיר

# --- הגדרות ניטור ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask('')
@app.route('/')
def home(): return f"Bot Active | Last Scan: {state.get('last_scan_duration', 0)}s"

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
        logger.error(f"Sheet Error: {e}")
        return None

state = {"last_settings": {}, "last_scan_duration": 0}

def fetch_price_parallel(ex_name, pair):
    """משיכת מחיר בודד עם טיימאאוט קצר למניעת תקיעה"""
    try:
        exchange = getattr(ccxt, ex_name)({'timeout': 7000}) # 7 שניות לכל בורסה
        ticker = exchange.fetch_ticker(pair)
        return ex_name, ticker['last'], ticker.get('quoteVolume', 0)
    except:
        return ex_name, None, 0

def master_cycle():
    global state
    start_time = time.time()
    doc = get_sheet_safe()
    if not doc: return 

    try:
        s_sheet = doc.worksheet("Settings")
        p_sheet = doc.worksheet("pairs")
        rows = s_sheet.get_all_values()
        
        current = {
            "scan_interval": rows[2][1] if len(rows) > 2 else "60",
            "target_volume": rows[3][1] if len(rows) > 3 else "1000",
            "target_profit": rows[4][1] if len(rows) > 4 else "0.5",
            "keep_alive_interval": rows[5][1] if len(rows) > 5 else "15",
            "exchanges": [ex.strip().lower() for ex in s_sheet.col_values(3)[1:] if ex.strip()],
            "pairs": [p.strip().upper() for p in p_sheet.col_values(1)[1:] if p.strip()]
        }
        state["last_settings"] = current

        # סריקה מקבילית לשיפור ביצועים
        profit_threshold = float(current['target_profit'])
        min_vol = float(current['target_volume'])

        for pair in current['pairs']:
            prices = {}
            # שימוש ב-Threadpool כדי לא לחכות בורסה-בורסה
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(fetch_price_parallel, ex, pair) for ex in current['exchanges']]
                for future in futures:
                    name, price, vol = future.result()
                    if price and vol >= min_vol:
                        prices[name] = price
            
            if len(prices) > 1:
                low_ex, high_ex = min(prices, key=prices.get), max(prices, key=prices.get)
                diff = ((prices[high_ex] - prices[low_ex]) / prices[low_ex]) * 100
                if diff >= profit_threshold:
                    bot.send_message(CHAT_ID, f"💰 **הזדמנות ארביטראז'!**\n\n🪙 מטבע: `{pair}`\n📊 פער: `{diff:.2f}%` \n🛒 {low_ex.upper()} ➔ 💎 {high_ex.upper()}")

        state["last_scan_duration"] = round(time.time() - start_time, 2)
    except Exception as e:
        logger.error(f"Cycle Error: {e}")

# --- פקודות שליטה ---

@bot.message_handler(commands=['set_profit', 'set_volume', 'set_scan', 'set_report'])
def update_excel_settings(message):
    try:
        cmd = message.text.split()[0].replace('/', '')
        val = message.text.split()[1]
        mapping = {'set_scan': 'B3', 'set_volume': 'B4', 'set_profit': 'B5', 'set_report': 'B6'}
        get_sheet_safe().worksheet("Settings").update_acell(mapping[cmd], str(val))
        bot.reply_to(message, f"✅ עדכון בוצע: `{cmd}` נקבע ל-`{val}`")
        master_cycle()
    except: bot.reply_to(message, "ℹ️ פורמט: `/set_profit 0.5` ")

@bot.message_handler(commands=['status'])
def cmd_status(message):
    ls = state.get("last_settings", {})
    msg = (f"⚙️ **סטטוס מערכת:**\n\n"
           f"⏱ סריקה: `{ls.get('scan_interval')}s` | 📊 ווליום: `${ls.get('target_volume')}`\n"
           f"📈 רווח: `{ls.get('target_profit')}%` | 📢 דיווח: `{ls.get('keep_alive_interval')}m` \n"
           f"⚡️ זמן סריקה אחרון: `{state.get('last_scan_duration')} שניות` \n\n"
           f"🏦 בורסות: `{', '.join(ls.get('exchanges', []))}`\n"
           f"🪙 מטבעות: `{len(ls.get('pairs', []))} סה''כ` ")
    bot.reply_to(message, msg)

@bot.message_handler(commands=['compare'])
def compare_menu(message):
    if not state["last_settings"].get("pairs"): return bot.reply_to(message, "⏳ טוען...")
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [types.InlineKeyboardButton(p, callback_data=f"c_{p}") for p in state["last_settings"]["pairs"]]
    markup.add(*btns)
    bot.send_message(message.chat.id, "🪙 **בחר מטבע להשוואה מהירה:**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('c_'))
def handle_c(call):
    pair = call.data.split('_')[1]
    exchanges = state["last_settings"].get("exchanges", [])
    msg = [f"🔎 **השוואת {pair}:**\n"]
    prices = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_price_parallel, ex, pair) for ex in exchanges]
        for f in futures:
            name, price, _ = f.result()
            if price:
                prices[name] = price
                msg.append(f"✅ `{name.upper()}`: {price}")
            else: msg.append(f"❌ `{name.upper()}`: שגיאה")
    
    if len(prices) > 1:
        diff = ((max(prices.values()) - min(prices.values())) / min(prices.values())) * 100
        msg.append(f"\n📊 פער: `{diff:.2f}%` ")
    bot.edit_message_text("\n".join(msg), call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=['force_reload'])
def force_reload(message):
    master_cycle()
    bot.reply_to(message, "✅ נתונים נטענו מחדש מהאקסל.")

# --- הפעלה בטוחה (Safe Polling) ---
if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(2)
    master_cycle()
    
    scheduler = BackgroundScheduler()
    # שימוש בערך מהאקסל לתזמון
    interval = int(state["last_settings"].get("scan_interval", 60))
    scheduler.add_job(master_cycle, 'interval', seconds=interval)
    scheduler.start()
    
    logger.info("Bot is running with high-performance settings...")
    bot.infinity_polling(timeout=25, long_polling_timeout=15)
