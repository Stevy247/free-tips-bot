import telebot
import os
import time
import logging
from datetime import datetime, timedelta
from telebot import types
from collections import defaultdict

# ====================== CONFIG ======================
import os

# === TEMPORARY FOR TESTING ON PHONE ===
TOKEN = os.getenv("TOKEN")

# If running on phone (Pydroid3), hardcode the token temporarily
if not TOKEN:
    TOKEN = "8233280525:AAEBE0aF0_EA0kmI-8KiBT7khackVbsnntw"   # ← Paste your real token here

print("TOKEN loaded:", bool(TOKEN))

if not TOKEN:
    raise ValueError("No TOKEN provided")

# ================== YOUR SETTINGS ==================
CHANNEL_ID = "-1001775169065"
CHANNEL_INVITE_LINK = "https://t.me/+NzZ2mbPo9_02MDk8"
ADMIN_ID = 8258407224
VIP_USERNAME = "Antonio_Gomez_01"

bot = telebot.TeleBot(TOKEN)
# ====================== LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ====================== STORAGE ======================
users_data = {}
all_users = set()
free_games_posts = []
daily_free_games = None
last_daily_reset = datetime.now().date()
last_action_time = defaultdict(lambda: datetime.min)

# ====================== HELPERS ======================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def is_member_of_channel(user_id: int) -> bool:
    if not CHANNEL_ID:
        return True
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

def get_referral_link(user_id: int) -> str:
    me = bot.get_me()
    if me.username:
        return f"https://t.me/{me.username}?start=ref_{user_id}"
    return "Bot username not set!"

def reset_invites_if_expired(user_id: int):
    if user_id not in users_data:
        return
    data = users_data[user_id]
    now = datetime.now()
    access_date = data.get("access_granted_date")
    if access_date and (now - access_date) > timedelta(days=7):
        data["invites"] = 0
        data["last_referral_date"] = None
        data["access_granted_date"] = None

def check_access(user_id: int) -> str:
    if is_admin(user_id):
        return "full"

    reset_invites_if_expired(user_id)
    
    if user_id not in users_data:
        users_data[user_id] = {
            "joined_channel": False,
            "invites": 0,
            "last_referral_date": None,
            "access_granted_date": None
        }
    
    data = users_data[user_id]
    
    if not data["joined_channel"]:
        return "channel"
    
    if data.get("access_granted_date"):
        if (datetime.now() - data["access_granted_date"]) <= timedelta(days=7):
            return "full"
        else:
            data["invites"] = 0
            data["access_granted_date"] = None
    
    if data["invites"] < 5:
        return "invites"
    
    data["access_granted_date"] = datetime.now()
    return "full"

def anti_spam(user_id: int, cooldown: int = 3) -> bool:
    now = datetime.now()
    if (now - last_action_time[user_id]) < timedelta(seconds=cooldown):
        return False
    last_action_time[user_id] = now
    return True

def daily_reset_check():
    global daily_free_games, last_daily_reset
    today = datetime.now().date()
    if today > last_daily_reset:
        if daily_free_games:
            free_games_posts.append(daily_free_games.copy())
        daily_free_games = None
        last_daily_reset = today

def get_persistent_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2, is_persistent=True)
    markup.add("🎮 Today's Free Games", "📜 Previous Free Games")
    markup.add("🏆 Referral Leaderboard", "💎 VIP Service")
    return markup

# ====================== BROADCAST NOTIFICATION ======================
@bot.message_handler(commands=['notify', 'broadcast'], func=lambda m: m.from_user.id == ADMIN_ID)
def send_notification(message):
    daily_reset_check()
    
    text = ""
    if message.caption:
        text = message.caption.replace('/notify', '').replace('/broadcast', '').strip()
    elif message.text:
        text = message.text.replace('/notify', '').replace('/broadcast', '').strip()
    
    media_file_id = None
    media_type = None
    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        media_file_id = message.video.file_id
        media_type = "video"
    elif message.reply_to_message:
        if message.reply_to_message.photo:
            media_file_id = message.reply_to_message.photo[-1].file_id
            media_type = "photo"
        elif message.reply_to_message.video:
            media_file_id = message.reply_to_message.video.file_id
            media_type = "video"
    
    if not text and not media_file_id:
        bot.reply_to(message, "📌 Usage:\n/notify Your message here\nOr attach photo/video + /notify in caption")
        return
    
    success_count = 0
    total = len(all_users)
    
    for user_id in list(all_users):
        try:
            if media_file_id and media_type == "photo":
                bot.send_photo(user_id, media_file_id, caption=text)
            elif media_file_id and media_type == "video":
                bot.send_video(user_id, media_file_id, caption=text)
            else:
                bot.send_message(user_id, text)
            success_count += 1
            time.sleep(0.05)
        except Exception as e:
            logger.warning(f"Failed to send notification to {user_id}: {e}")
    
    bot.reply_to(message, f"✅ Notification sent to **{success_count}/{total}** users.", parse_mode="Markdown")

# ====================== POST FREE GAMES (FIXED) ======================
@bot.message_handler(commands=['post'], func=lambda m: m.from_user.id == ADMIN_ID)
def post_free_games(message):
    global daily_free_games
    daily_reset_check()
    
    # Get caption text (remove /post command)
    text = ""
    if message.caption:
        text = message.caption.replace('/post', '').strip()
    elif message.text:
        text = message.text.replace('/post', '').strip()
    
    media_file_id = None
    media_type = None
    
    # Get media from current message or replied message
    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        media_file_id = message.video.file_id
        media_type = "video"
    elif message.reply_to_message:
        if message.reply_to_message.photo:
            media_file_id = message.reply_to_message.photo[-1].file_id
            media_type = "photo"
        elif message.reply_to_message.video:
            media_file_id = message.reply_to_message.video.file_id
            media_type = "video"
    
    if media_file_id or text:
        daily_free_games = {
            "text": text or "Today's Free Games",
            "media": media_file_id,
            "media_type": media_type
        }
        
        bot.reply_to(message, f"✅ Today's Free Games saved successfully!\n"
                             f"Type: {media_type or 'Text only'}\n"
                             f"Caption: {text[:100]}..." if text else "No caption")
        
        # Preview for admin
        try:
            if media_file_id and media_type == "photo":
                bot.send_photo(message.chat.id, media_file_id, caption=text or "Today's Free Games")
            elif media_file_id and media_type == "video":
                bot.send_video(message.chat.id, media_file_id, caption=text or "Today's Free Games")
            else:
                bot.send_message(message.chat.id, text or "Today's Free Games")
        except:
            pass
    else:
        bot.reply_to(message, "❌ Nothing to post.\n\n"
                             "How to post:\n"
                             "1. Send a photo/video + write /post in the caption\n"
                             "2. Or reply to a photo/video with /post Your text here")

# ====================== START ======================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    all_users.add(user_id)
    daily_reset_check()
    
    # Referral handling (unchanged)
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer = int(args[1][4:])
            if referrer != user_id and referrer in users_data:
                reset_invites_if_expired(referrer)
                users_data[referrer]["invites"] += 1
                users_data[referrer]["last_referral_date"] = datetime.now()
                
                if users_data[referrer]["invites"] >= 5 and not users_data[referrer].get("access_granted_date"):
                    bot.send_message(referrer, "🎉 Congratulations! You now have 7 days access to Today's Free Games!")
                
                bot.send_message(referrer, f"🎉 New referral! Total invites: {users_data[referrer]['invites']}/5")
        except:
            pass
    
    if user_id not in users_data and not is_admin(user_id):
        users_data[user_id] = {
            "joined_channel": False,
            "invites": 0,
            "last_referral_date": None,
            "access_granted_date": None
        }
    
    access = check_access(user_id)
    
    if access == "channel" and not is_admin(user_id):
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("✅ Join Private Channel", url=CHANNEL_INVITE_LINK))
        markup.add(types.InlineKeyboardButton("🔄 I Have Joined", callback_data="check_channel"))
        
        bot.send_message(
            message.chat.id,
            "👋 Welcome to Free Tips Bot!\n\n"
            "You must Join our private channel to use me. Join below 👇.",
            reply_markup=markup
        )
    else:
        bot.send_message(
            message.chat.id,
            "✅ Main menu unlocked!\nUse the buttons at the bottom.",
            reply_markup=get_persistent_keyboard()
        )

# ====================== BOTTOM MENU HANDLER ======================
@bot.message_handler(content_types=['text'])
def handle_keyboard(message):
    user_id = message.from_user.id
    text = message.text.strip()
    daily_reset_check()
    
    if text == "🎮 Today's Free Games":
        access = check_access(user_id)
        if access == "full":
            if daily_free_games:
                media = daily_free_games.get("media")
                media_type = daily_free_games.get("media_type")
                caption = daily_free_games.get("text", "")
                
                if media and media_type == "photo":
                    bot.send_photo(message.chat.id, media, caption=caption)
                elif media and media_type == "video":
                    bot.send_video(message.chat.id, media, caption=caption)
                else:
                    bot.send_message(message.chat.id, caption)
            else:
                bot.send_message(message.chat.id, "No daily free games posted yet.")
        else:
            invites = users_data.get(user_id, {}).get("invites", 0)
            days_left = 0
            if users_data.get(user_id, {}).get("access_granted_date"):
                days_left = 7 - (datetime.now() - users_data[user_id]["access_granted_date"]).days
            
            ref_link = get_referral_link(user_id)
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("🔗 Share to Friends", callback_data=f"share_ref_{user_id}"))
           
            bot.send_message(
                message.chat.id,
                f"❌ Access required: **5 Friends**\n\n"
                f"Current invites: `{invites}/5`\n"
                f"Days left: `{days_left if days_left > 0 else 'Expired'}`\n\n"
                "Invite more friends to reactivate access:",
                parse_mode="Markdown",
                reply_markup=markup
            )
    
    elif text == "📜 Previous Free Games":
        if free_games_posts:
            bot.send_message(message.chat.id, "📜 **Last 6 Free Games Posts:**", parse_mode="Markdown")
            for post in reversed(free_games_posts[-6:]):
                media = post.get("media")
                media_type = post.get("media_type")
                caption = post.get("text", "")
                
                if media and media_type == "photo":
                    bot.send_photo(message.chat.id, media, caption=caption)
                elif media and media_type == "video":
                    bot.send_video(message.chat.id, media, caption=caption)
                else:
                    bot.send_message(message.chat.id, caption)
        else:
            bot.send_message(message.chat.id, "No previous posts yet.")
    
    # Other buttons unchanged...
    elif text == "🏆 Referral Leaderboard":
        if users_data:
            sorted_list = sorted(users_data.items(), key=lambda x: x[1].get("invites", 0), reverse=True)
            lb = "🏆 **Top Referrers**\n\n"
            for i, (uid, data) in enumerate(sorted_list[:10], 1):
                lb += f"{i}. `{uid}` — **{data.get('invites', 0)}** invites\n"
            bot.send_message(message.chat.id, lb, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "No referrals yet.")
    
    elif text == "💎 VIP Service":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Contact Admin", url=f"https://t.me/{VIP_USERNAME}"))
        bot.send_message(message.chat.id, "💎 Want VIP Service?\nContact me for premium access.", 
                        reply_markup=markup)

# ====================== CALLBACKS ======================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    if not anti_spam(user_id):
        bot.answer_callback_query(call.id, "⏳ Please wait a moment.", show_alert=True)
        return
    
    daily_reset_check()
    
    if call.data == "check_channel":
        if is_member_of_channel(user_id) or is_admin(user_id):
            if not is_admin(user_id):
                users_data[user_id]["joined_channel"] = True
            bot.edit_message_text(
                "✅ You have successfully joined the channel!\nMain menu unlocked.",
                call.message.chat.id, call.message.message_id
            )
            bot.send_message(
                call.message.chat.id,
                "Use the buttons below to navigate:",
                reply_markup=get_persistent_keyboard()
            )
            all_users.add(user_id)
        else:
            bot.answer_callback_query(call.id, "❌ Please join the channel first.", show_alert=True)                                          
            # ====================== SHARE REFERRAL CALLBACK ======================
@bot.callback_query_handler(func=lambda call: call.data.startswith("share_ref_"))
def handle_share_referral(call):
    try:
        user_id = int(call.data.split("_")[-1])
        ref_link = get_referral_link(user_id)
        
        bot.answer_callback_query(call.id, "✅ Opening share...", show_alert=False)
        
        bot.send_message(
            call.message.chat.id,
            f"🔗 **Your Personal Referral Link**\n\n"
            f"{ref_link}\n\n"
            "📤 Tap and hold the link above → **Forward** or **Copy** and send to your friends.\n"
            "When they join using this link, you get +1 invite!",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Something went wrong", show_alert=True)
            
# ====================== BOT START ======================
if __name__ == "__main__":
    logger.info("🤖 Free Tips Bot starting...")
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(2)
    except:
        pass
    
    logger.info("🚀 Bot started!")
    
    while True:
        try:
            bot.infinity_polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(10)
