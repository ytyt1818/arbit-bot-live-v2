import os
import time
import json
import logging
import telebot
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# הגדרת לוגים למניעת ניחושים
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- משיכת משתני סביבה מה-Render שלך ---
# שימוש בשמות המדויקים שמופיעים בצילום המסך image_254102.png
TOKEN = os.getenv('TELEGRAM_TOKEN') 
JSON_CREDS = os.getenv('GSPREAD_CREDENTIALS')
SPREADSHEET_ID = "1W29_M8Wv_hEitYv3S6u7p_x9-y6x0Z4Nq3L-y0V8Y_I" # ה-ID מה-URL שלך
SHEET_NAME = "Settings" # השם המדויק מהאקסל שלך (image_24be54.png)

# אתחול הבוט
bot = telebot.TeleBot(TOKEN)

class ArbitrageSystem:
    def __init__(self):
        self.client = None
        self.sheet = None
        self.creds = self._prepare_creds()

    def _prepare_creds(self):
        """הכנת אישורים מתוך משתנה הסביבה של Render"""
        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds_dict = json.loads(JSON_CREDS)
            return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        except Exception as e:
            logger.error(f"Failed to parse GSPREAD_CREDENTIALS: {e}")
            return None

    def connect(self):
        """חיבור אקטיבי לגיליון Settings עם מנגנון Reconnect"""
        try:
            self.client = gspread.authorize(self.creds)
            # פתיחה לפי השם המדויק שמופיע באקסל שלך
            self.sheet = self.client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
            logger.info(f"Successfully connected to sheet: {SHEET_NAME}")
            return True
        except Exception as e:
            logger.error(f"Connection error to {SHEET_NAME}: {e}")
            return False

    def get_settings_data(self):
        """משיכת נתונים מהגיליון עם טיפול בשגיאות רשת"""
        try:
            if not self.sheet: self.connect()
            return self.sheet.get_all_records()
        except Exception as e:
            logger.warning("Session expired. Reconnecting...")
            if self.connect():
                return self.sheet.get_all_records()
            return None

# אתחול המערכת
sys_manager = ArbitrageSystem()

# --- פקודות טלגרם (חיווי בפרטי ובקבוצה) ---

@bot.message_handler(commands=['status'])
def handle_status(message):
    data = sys_manager.get_settings_data()
    if data:
        # יצירת הודעה מעוצבת לפי הנתונים שרואים ב-image_24be54.png
        msg = f"📊 *Arbit-Bot-Live-v2* (Sheet: {SHEET_NAME})\n\n"
        for row in data:
            name = row.get('Setting Name (A)', 'Unknown')
            val = row.get('Value (B)', 'N/A')
            msg += f"⚙️ *{name}*: `{val}`\n"
        
        bot.reply_to(message, msg, parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ שגיאת סינכרון: וודא שה-APIs מופעלים וההרשאות תקינות.")

# --- הרצה יציבה עם Auto-Restart ---

if __name__ == "__main__":
    logger.info("System initializing...")
    sys_manager.connect()
    
    while True:
        try:
            logger.info("Bot is polling...")
            bot.polling(none_stop=True, interval=0, timeout=40)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(10) # המתנה לפני ניסיון חוזר
