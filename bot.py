import telebot, time, os, ccxt, threading, logging, gspread, json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from flask import Flask
from concurrent.futures import ThreadPoolExecutor

# 1. תשתית וניטור
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
@app.route('/')
def health(): return "SYSTEM_STABLE", 200

TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')
G_CREDS = os.getenv('GSPREAD_CREDENTIALS')
bot = telebot.TeleBot(TOKEN)

# 2. זיכרון מערכת אחוד (C2-C5)
state = {
    "interval": 60, "volume_min": 100, "profit_target": 0.3, "fees": 0.1,
    "exchanges": [], "pairs": [], "last_heartbeat": None,
    "active_instances": {}, "last_sync_success": False
}

def get_now(): return (datetime.utcnow() + timedelta(hours=2))

# 3. מנוע סנכרון (C2, C3, C4, C5, E, G, H)
def sync_data():
    try:
        if not G_CREDS: return False
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(G_CREDS), scope)
        client = gspread.authorize(creds)
        sheet = client.open("CryptoBot_Config").worksheet("settings")
        data = sheet.get_all_values()

        # עדכון פרמטרים
        state["interval"] = max(15, int(data[1][2])) # C2
        state["volume_min"] = float(data[2][2])      # C3
        state["profit_target"] = float(data[3][2])   # C4
        state["fees"] = float(data[4][2])            # C5

        state["exchanges"] = [row[4].lower().strip() for row in data[1:] if len(row) > 4 and row[4]]
        state["pairs"] = [row[6] for row in data[1:] if len(row) > 7 and row[7] == 'V']
        
        for ex in state["exchanges"]:
            if ex not in state["active_instances"] and hasattr(ccxt, ex):
                state["active_instances"][ex] = getattr(ccxt, ex)({'enableRateLimit': True})
        
        state["last_sync_success"] = True
        return True
    except Exception as e:
        logger.error(f"Sync Failure: {e}")
        return False

# 4. מנוע סריקה עם תצוגת נזילות (Liquidity)
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
                    bot.send_message(CHAT_ID, f"💓 *Heartbeat:* המערכת פעילה.\nזמן סנכרון: `{now.strftime('%H:%M')}`", parse_mode='Markdown')
                    state["last_heartbeat"] = now

                # לוגיקת ארביטראז'
                if state["pairs"] and state["active_instances"]:
                    for symbol in state["pairs"]:
                        def fetch(ex_id):
                            try:
                                t = state["active_instances"][ex_id].fetch_ticker(symbol)
                                vol_usd = t['bidVolume'] * t['bid']
                                return {'id': ex_id, 'bid': t['bid'], 'ask': t['ask'], 'vol': vol_usd}
                            except: return None

                        with ThreadPoolExecutor(max_workers=5) as executor:
                            res = [r for r in executor.map(fetch, state["active_instances"].keys()) if r]

                        if len(res) > 1:
                            low = min(res, key=lambda x: x['ask'])
                            high = max(res, key=lambda x: x['bid'])
                            
                            # סינון לפי נפח (ד)
                            if low['vol'] < state["volume_min"] or high['vol'] < state["volume_min"]:
                                continue

                            raw_p = ((high['bid'] - low['ask']) / low['ask']) * 100
                            net_p = raw_p - state["fees"]

                            if net_p >= state["profit_target"]:
                                msg = (f"💰 *רווח נטו: {net_p:.2f}%*\n"
                                       f"🪙 מטבע: `{symbol}`\n"
                                       f"🛒 קנייה ב-{low['id'].upper()}: `{low['ask']}`\n"
                                       f"💎 מכירה ב-{high['id'].upper()}: `{high['bid']}`\n"
                                       f"🌊 נזילות זמינה: `${min(low['vol'], high['vol']):,.0f}`")
                                bot.send_message(CHAT_ID, msg, parse_mode='Markdown')

            time.sleep(state["interval"])
        except Exception as e:
            logger.error(f"Scanner error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=10000), daemon=True).start()
    bot.remove_webhook()
    time.sleep(2)
    bot.send_message(CHAT_ID, "🚀 *Master Build V1.2 (Final)*\nכולל נזילות, עמלות נטו וסנכרון מלא.", parse_mode='Markdown')
    run_scanner()
