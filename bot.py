import telebot
import os
import time
import logging
from datetime import datetime, timedelta
from telebot import types
from collections import defaultdict

# ====================== CONFIG ======================
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    TOKEN = "8233280525:AAHP9UvR11BepegIkcHE2SHFvzQ9Roj6XDk"

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
users_data = {}                    # user_id → user data (for access system)
all_users = set()                  # NEW: Track all unique user IDs for notifications
free_games_posts = []
daily_free_games = None
last_daily_reset = datetime.now().date()
last_action_time = defaultdict(lambda: datetime.min)

# ====================== HELPERS ======================
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
    return f"https://t.me/{me.username}?start=ref_{user_id}" if me.username else "Bot username not set!"


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
        logger.info(f"Access expired for user {user_id} after 7 days")


def check_access(user_id: int) -> str:
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
    
    # Get text
    if message.caption:
        text = message.caption.replace('/notify', '').replace('/broadcast', '').strip()
    else:
        text = message.text.replace('/notify', '').replace('/broadcast', '').strip() if message.text else ""
    
    # Get media (photo or video)
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
        bot.reply_to(message, "📌 Usage:\n/notify Your notification message here\n"
                             "Or attach photo/video + /notify in caption")
        return
    
    # Send to all users
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
            time.sleep(0.05)  # Avoid hitting Telegram rate limits
        except Exception as e:
            logger.warning(f"Failed to send notification to {user_id}: {e}")
            # Optionally remove blocked users: all_users.discard(user_id)
    
    bot.reply_to(message, f"✅ Notification sent to **{success_count}/{total}** users.", parse_mode="Markdown")


# ====================== START ======================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    # NEW: Track user for notifications
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
    
    if user_id not in users_data:
        users_data[user_id] = {
            "joined_channel": False,
            "invites": 0,
            "last_referral_date": None,
            "access_granted_date": None
        }
    
    access = check_access(user_id)
    
    if access == "channel":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("✅ Join Private Channel", url=CHANNEL_INVITE_LINK))
        markup.add(types.InlineKeyboardButton("🔄 I Have Joined", callback_data="check_channel"))
        
        bot.send_message(
            message.chat.id,
            "👋 Welcome to Free Tips Bot!\n\n"
            "You must Join our private channel,in other to Use me Join below 👇.",
            reply_markup=markup
        )
    else:
        bot.send_message(
            message.chat.id,
            "✅ Main menu unlocked!\nUse the buttons at the bottom.",
            reply_markup=get_persistent_keyboard()
        )


# ====================== POST HANDLER (Photos + Videos) ======================
@bot.message_handler(commands=['post'], func=lambda m: m.from_user.id == ADMIN_ID)
def post_free_games(message):
    global daily_free_games
    daily_reset_check()
    
    if message.caption:
        text = message.caption.replace('/post', '').strip()
    else:
        text = message.text.replace('/post', '').strip() if message.text else ""
    
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
    
    if text or media_file_id:
        daily_free_games = {
            "text": text or "Today's Free Games",
            "media": media_file_id,
            "media_type": media_type
        }
        bot.reply_to(message, f"✅ Today's Free Games posted! ({media_type or 'text only'})")
        
        # Preview
        if media_file_id and media_type == "photo":
            bot.send_photo(message.chat.id, media_file_id, caption=text or "Today's Free Games")
        elif media_file_id and media_type == "video":
            bot.send_video(message.chat.id, media_file_id, caption=text or "Today's Free Games")
        else:
            bot.send_message(message.chat.id, text or "Today's Free Games")
    else:
        bot.reply_to(message, "📌 Correct ways:\n1. Attach photo/video + /post in caption\n2. Reply to media with /post text")


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
            markup = types.InlineKeyboardMarkup()
            text = "Hello 👋 Friends get free games daily on this AI bot and start winning 👇 " + ref_link 
            markup.add(types.InlineKeyboardButton("🔗 Share to Friends", url=text))
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
        if is_member_of_channel(user_id):
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
            logger.info(f"User {user_id} joined channel")
            all_users.add(user_id)  # Also track on callback
        else:
            bot.answer_callback_query(call.id, "❌ Please join the channel using the button first 🙏 If you have send Request, then pls wait Small.", show_alert=True)


# ====================== BOT START ======================
if __name__ == "__main__":
    logger.info("🤖 Free Tips Bot starting with 7-day access system + notifications...")
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(2)
        logger.info("✅ Webhook removed")
    except Exception as e:
        logger.warning(f"Webhook removal: {e}")
    
    logger.info("🚀 Bot started!")
    
    while True:
        try:
            bot.infinity_polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(10)
