import telebot, time, os, ccxt, threading, logging, gspread, json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from flask import Flask
from concurrent.futures import ThreadPoolExecutor

# 1. ניטור לוגים מקצועי
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# 2. שרת בריאות חיוני עבור Render
app = Flask(__name__)
@app.route('/')
def health(): return "SYSTEM_ONLINE", 200

# 3. משיכת משתנים מהגדרות ה-Environment שלך
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
PORT = int(os.getenv('PORT', 10000))
bot = telebot.TeleBot(TOKEN)

state = {
    "interval": 60,
    "profit": 0.3,
    "exchanges": [],
    "pairs": [],
    "is_running": True
}

def get_israel_time():
    return (datetime.utcnow() + timedelta(hours=2)).strftime('%H:%M:%S')

# 4. סנכרון מול Google Sheets (שימוש במפתח GSPREAD_CREDENTIALS)
def sync_from_google():
    try:
        # התאמה מדויקת לשם המפתח שב-Render
        creds_json = os.getenv('GSPREAD_CREDENTIALS')
        if not creds_json:
            logger.error("Missing GSPREAD_CREDENTIALS key!")
            return

        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("CryptoBot_Config").worksheet("settings")
        
        # קריאת נתונים ודיווח על שינויים לקבוצה
        new_prof = float(sheet.acell('C4').value)
        if new_prof != state["profit"]:
            if CHAT_ID:
                bot.send_message(CHAT_ID, f"🔄 *עדכון אקסל:* סף רווח שונה ל-`{new_prof}%`", parse_mode='Markdown')
            state["profit"] = new_prof
        
        state["interval"] = int(sheet.acell('C2').value)
        state["exchanges"] = [ex.lower().strip() for ex in sheet.col_values(5)[1:] if ex]
        
        p_list, s_list = sheet.col_values(7)[1:], sheet.col_values(8)[1:]
        state["pairs"] = [p for p, s in zip(p_list, s_list) if s == 'V']
        
        logger.info("Google Sheets Sync: Success")
    except Exception as e:
        logger.error(f"Sync error: {e}")

# 5. מנוע הארביטראז' המקבילי
def arbitrage_monitor():
    while True:
        sync_from_google()
        if state["is_running"] and CHAT_ID and state["pairs"]:
            try:
                # אתחול בורסות דינמי
                instances = {ex: getattr(ccxt, ex)({'enableRateLimit': True}) for ex in state["exchanges"]}
                
                for symbol in state["pairs"]:
                    def fetch(ex_id):
                        try:
                            t = instances[ex_id].fetch_ticker(symbol)
                            return {'id': ex_id, 'bid': t['bid'], 'ask': t['ask']}
                        except: return None

                    with ThreadPoolExecutor(max_workers=len(instances)) as exe:
                        res = [r for r in exe.map(fetch, instances.keys()) if r]

                    if len(res) > 1:
                        low, high = min(res, key=lambda x: x['ask']), max(res, key=lambda x: x['bid'])
                        profit = ((high['bid'] - low['ask']) / low['ask']) * 100
                        if profit >= state["profit"]:
                            bot.send_message(CHAT_ID, 
                                f"💰 *הזדמנות רווח! {profit:.2f}%*\n🪙 `{symbol}`\n🛒 {low['id']}: {low['ask']}\n💎 {high['id']}: {high['bid']}", 
                                parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Engine loop error: {e}")
        time.sleep(state["interval"])

# 6. הרצה חסינה
if __name__ == "__main__":
    # הפעלת שרת Port 10000 (מניעת קריסת Render)
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT), daemon=True).start()
    
    # ניקוי Webhook למניעת Conflict 409
    bot.remove_webhook()
    time.sleep(2)
    
    # הודעת הפעלה לקבוצה
    if CHAT_ID:
        bot.send_message(CHAT_ID, f"🚀 *המערכת עלתה לאוויר בהצלחה!*\nזמן: `{get_israel_time()}`", parse_mode='Markdown')
    
    # הפעלת המנוע
    threading.Thread(target=arbitrage_monitor, daemon=True).start()
    
    # תחילת האזנה לטלגרם
    bot.infinity_polling(timeout=25)
