import telebot, time, os, ccxt, threading, logging, gspread, json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from flask import Flask
from concurrent.futures import ThreadPoolExecutor

# 1. הגדרות תשתית (ז)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
@app.route('/')
def health(): return "SYSTEM_OPERATIONAL", 200

# משיכת משתני סביבה מה-Render (cite: image_8d9140.png)
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
G_CREDS = os.getenv('GSPREAD_CREDENTIALS')
bot = telebot.TeleBot(TOKEN)

# 2. זיכרון מערכת אחוד
state = {
    "interval": 60, "volume_min": 100, "profit_target": 0.3, "fees": 0.1,
    "exchanges": [], "pairs": [], "last_heartbeat": None,
    "active_instances": {}, "last_sync_success": False
}

def get_now(): return (datetime.utcnow() + timedelta(hours=2))

# 3. מנוע סנכרון גוגל שיטס (C2, C3, C4, C5, E, G, H)
def sync_data():
    try:
        if not G_CREDS: return False
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(G_CREDS), scope)
        client = gspread.authorize(creds)
        sheet = client.open("CryptoBot_Config").worksheet("settings")
        data = sheet.get_all_values()

        # עדכון פרמטרים ודיווח שינויים (א+ה)
        new_int = max(15, int(data[1][2])) # C2
        new_vol = float(data[2][2])        # C3
        new_prof = float(data[3][2])       # C4
        new_fees = float(data[4][2])       # C5

        if new_prof != state["profit_target"] or new_int != state["interval"]:
            bot.send_message(CHAT_ID, f"🔄 *עדכון אוטומטי מהאקסל:*\nרווח יעד נטו: `{new_prof}%` | תדירות: `{new_int}s`", parse_mode='Markdown')
        
        state.update({"interval": new_int, "volume_min": new_vol, "profit_target": new_prof, "fees": new_fees})

        # עדכון בורסות ומטבעות (E, G, H)
        state["exchanges"] = [row[4].lower().strip() for row in data[1:] if len(row) > 4 and row[4]]
        state["pairs"] = [row[6] for row in data[1:] if len(row) > 7 and row[7] == 'V']
        
        # אתחול/עדכון חיבורי בורסה (ג)
        for ex in state["exchanges"]:
            if ex not in state["active_instances"] and hasattr(ccxt, ex):
                state["active_instances"][ex] = getattr(ccxt, ex)({'enableRateLimit': True})
        
        state["last_sync_success"] = True
        logger.info(f"Sync Success: Monitoring {len(state['pairs'])} pairs.")
        return True
    except Exception as e:
        logger.error(f"Sync Failure: {e}")
        state["last_sync_success"] = False
        return False

# 4. מנוע סריקת ארביטראז' (ד+ה)
def run_scanner():
    while True:
        try:
            if sync_data():
                now = get_now()
                # דו"ח בוקר (א)
                if now.hour == 8 and now.minute == 0:
                    bot.send_message(CHAT_ID, "☀️ *דו\"ח בוקר:* המערכת סורקת כסדרה.", parse_mode='Markdown')
                    time.sleep(60)

                # הודעת דופק (ב)
                if not state["last_heartbeat"] or (now - state["last_heartbeat"]).seconds > 3600:
                    bot.send_message(CHAT_ID, f"💓 *Heartbeat:* המערכת פעילה.\nסנכרון תקין: `{now.strftime('%H:%M')}`", parse_mode='Markdown')
                    state["last_heartbeat"] = now

                # לוגיקת סריקת מחירים
                if state["pairs"] and state["active_instances"]:
                    for symbol in state["pairs"]:
                        def fetch(ex_id):
                            try:
                                t = state["active_instances"][ex_id].fetch_ticker(symbol)
                                if (t['bidVolume'] * t['bid']) < state["volume_min"]: return None
                                return {'id': ex_id, 'bid': t['bid'], 'ask': t['ask']}
                            except: return None

                        with ThreadPoolExecutor(max_workers=5) as executor:
                            res = [r for r in executor.map(fetch, state["active_instances"].keys()) if r]

                        if len(res) > 1:
                            low, high = min(res, key=lambda x: x['ask']), max(res, key=lambda x: x['bid'])
                            raw_p = ((high['bid'] - low['ask']) / low['ask']) * 100
                            net_p = raw_p - state["fees"]
                            if net_p >= state["profit_target"]:
                                bot.send_message(CHAT_ID, f"💰 *רווח נטו: {net_p:.2f}%*\n🪙 `{symbol}`\n🛒 {low['id'].upper()} -> 💎 {high['id'].upper()}", parse_mode='Markdown')

            time.sleep(state["interval"])
        except Exception as e:
            logger.error(f"Loop Error: {e}")
            time.sleep(30) # השהייה במקרה של תקלה כללית (ו)

# 5. נקודת כניסה
if __name__ == "__main__":
    # הפעלת שרת בריאות ל-Render
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=10000), daemon=True).start()
    
    # ניקוי Webhook למניעת Conflict 409
    bot.remove_webhook()
    time.sleep(2)
    
    bot.send_message(CHAT_ID, "🚀 *Master Build V1.1* עלה לאוויר בשלמותו.\nמצב אוטונומי פעיל.", parse_mode='Markdown')
    
    run_scanner()
