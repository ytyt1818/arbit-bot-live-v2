import os
import json
import gspread
import telebot
import time
import requests
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials

# הגדרות בסיסיות ממשתני הסביבה של Render
TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
bot = telebot.TeleBot(TOKEN)

# "זיכרון" הבוט לזיהוי שינויים וניהול זמן
last_settings = {}
last_keep_alive_time = datetime.now() - timedelta(hours=24)

def get_sheets_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get('GSPREAD_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- פונקציות "מתורגמן" למשיכת מחירים מהבורסות ---

def get_price_mexc(symbol):
    try:
        url = f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol.replace('/', '')}"
        return float(requests.get(url, timeout=5).json()['price'])
    except: return None

def get_price_bingx(symbol):
    try:
        url = f"https://open-api.bingx.com/openApi/swap/v2/quote/price?symbol={symbol.replace('/', '-')}"
        return float(requests.get(url, timeout=5).json()['data']['price'])
    except: return None

def get_price_xt(symbol):
    try:
        url = f"https://fapi.xt.com/future/market/v1/public/q/ticker?symbol={symbol.replace('/', '_').lower()}"
        return float(requests.get(url, timeout=5).json()['result']['p'])
    except: return None

def get_price_bitmart(symbol):
    try:
        url = f"https://api-cloud.bitmart.com/spot/v1/ticker?symbol={symbol.replace('/', '_')}"
        res = requests.get(url, timeout=5).json()
        return float(res['data']['tickers'][0]['last_price'])
    except: return None

def get_price_kucoin(symbol):
    try:
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol.replace('/', '-')}"
        res = requests.get(url, timeout=5).json()
        return float(res['data']['price'])
    except: return None

# --- לוגיקת הסריקה המרכזית ---

def run_arbitrage_cycle():
    global last_settings, last_keep_alive_time
    try:
        client = get_sheets_client()
        spreadsheet = client.open("arbit-bot-live_Control_Panel")
        settings_sheet = spreadsheet.worksheet("Settings")
        pairs_sheet = spreadsheet.worksheet("pairs")
        
        # קריאת הגדרות נוכחיות מהאקסל
        current_settings = {
            "interval": settings_sheet.acell('B3').value,
            "liquidity": settings_sheet.acell('B4').value,
            "profit": settings_sheet.acell('B5').value,
            "keep_alive": settings_sheet.acell('B6').value
        }
        
        # בדיקה ודיווח על שינויים בהגדרות
        if last_settings and current_settings != last_settings:
            changes = []
            if current_settings["interval"] != last_settings["interval"]:
                changes.append(f"⏱ זמן סריקה: {last_settings['interval']} -> {current_settings['interval']} שניות")
            if current_settings["profit"] != last_settings["profit"]:
                changes.append(f"🎯 רווח מטרה: {last_settings['profit']}% -> {current_settings['profit']}%")
            if current_settings["keep_alive"] != last_settings["keep_alive"]:
                changes.append(f"💓 Keep-alive: {last_settings['keep_alive']} -> {current_settings['keep_alive']} דקות")
            
            if changes:
                bot.send_message(CHAT_ID, "⚙️ **זוהה שינוי בהגדרות האקסל:**\n\n" + "\n".join(changes), parse_mode='Markdown')
        
        last_settings = current_settings
        min_profit = float(current_settings["profit"])
        
        # זיהוי בורסות פעילות מעמודה C
        active_exchanges = [val.lower().strip() for val in settings_sheet.col_values(3)[1:] if val]
        
        # קריאת רשימת צמדים
        pairs = pairs_sheet.col_values(1)[1:]
        
        for pair in pairs:
            prices = {}
            if "mexc" in active_exchanges: prices["Mexc"] = get_price_mexc(pair)
            if "bingx" in active_exchanges: prices["BingX"] = get_price_bingx(pair)
            if "xt" in active_exchanges: prices["XT"] = get_price_xt(pair)
            if "bitmart" in active_exchanges: prices["BitMart"] = get_price_bitmart(pair)
            if "kucoin" in active_exchanges: prices["KuCoin"] = get_price_kucoin(pair)
            
            # ניקוי בורסות שלא החזירו מחיר
            prices = {k: v for k, v in prices.items() if v is not None}
            
            if len(prices) >= 2:
                highest_name = max(prices, key=prices.get)
                lowest_name = min(prices, key=prices.get)
                diff_percent = (prices[highest_name] - prices[lowest_name]) / prices[lowest_name] * 100
                net_profit = diff_percent - 0.2 # קיזוז עמלות משוער
                
                if net_profit >= min_profit:
                    msg = (
                        f"💎 **הזדמנות ארביטראז'!**\n"
                        f"צמד: `{pair}`\n"
                        f"רווח נקי: **{net_profit:.2f}%**\n\n"
                        f"🛒 קנייה ב-{lowest_name}: {prices[lowest_name]}\n"
                        f"💰 מכירה ב-{highest_name}: {prices[highest_name]}"
                    )
                    bot.send_message(CHAT_ID, msg, parse_mode='Markdown')

        # מנגנון Keep-alive
        now = datetime.now()
        keep_alive_min = int(current_settings["keep_alive"])
        if now - last_keep_alive_time >= timedelta(minutes=keep_alive_min):
            bot.send_message(CHAT_ID, f"🔄 **הבוט סורק:** {len(pairs)} צמדים ב-{len(active_exchanges)} בורסות.\nיעד רווח נוכחי: {min_profit}%")
            last_keep_alive_time = now

        return int(current_settings["interval"])

    except Exception as e:
        print(f"Error in cycle: {e}")
        return 120

if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🚀 **arbit-bot-live הופעל!**\nהבוט מחובר לאקסל ומתחיל בסריקה.")
    while True:
        wait_time = run_arbitrage_cycle()
        time.sleep(wait_time)
