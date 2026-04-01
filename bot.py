import telebot
import os
import time
import logging
from datetime import datetime, timedelta
from telebot import types
from collections import defaultdict

# ====================== CONFIG ======================
TOKEN = os.getenv("TOKEN")

# Temporary for testing on phone (Pydroid3)
if not TOKEN:
    TOKEN = "8233280525:AAEBE0aF0_EA0kmI-8KiBT7khackVbsnntw"   # ← Use env var on Railway

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

today_free_games = []        # Multiple posts today
free_games_posts = []        # Previous days archive
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
    global last_daily_reset
    today = datetime.now().date()
    
    if today > last_daily_reset:
        if today_free_games:
            free_games_posts.append(today_free_games.copy())
            if len(free_games_posts) > 30:
                free_games_posts.pop(0)
        today_free_games.clear()
        last_daily_reset = today

def get_persistent_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2, is_persistent=True)
    markup.add("🎮 Today's Free Games", "📜 Previous Free Games")
    markup.add("🏆 Referral Leaderboard", "💎 VIP Service")
    return markup

# ====================== AUTO WELCOME WHEN APPROVED IN CHANNEL ======================
@bot.chat_member_handler()
def handle_channel_approval(update):
    try:
        if str(update.chat.id) != CHANNEL_ID:
            return
            
        old_status = update.old_chat_member.status
        new_status = update.new_chat_member.status
        user = update.new_chat_member.user
        user_id = user.id
        
        # Detect when user is approved (status changes to member/creator)
        if old_status in ["left", "kicked", "restricted"] and new_status in ["member", "administrator", "creator"]:
            username = f"@{user.username}" if user.username else user.first_name or "User"
            
            welcome_text = f"Hello, {username} you have been Approved in the private channel\n" \
                          f"You can now use the bot\nThanks 👍"
            
            try:
                bot.send_message(user_id, welcome_text)
                logger.info(f"Sent approval welcome to {user_id} (@{user.username})")
                
                # Mark as joined
                if user_id not in users_data:
                    users_data[user_id] = {"joined_channel": False, "invites": 0, "last_referral_date": None, "access_granted_date": None}
                users_data[user_id]["joined_channel"] = True
                all_users.add(user_id)
            except Exception as e:
                logger.warning(f"Could not send welcome to {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error in approval handler: {e}")

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

# ====================== POST MULTIPLE FREE GAMES ======================
@bot.message_handler(commands=['post'], func=lambda m: m.from_user.id == ADMIN_ID)
def post_free_games(message):
    daily_reset_check()
    
    text = ""
    if message.caption:
        text = message.caption.replace('/post', '').strip()
    elif message.text:
        text = message.text.replace('/post', '').strip()
    
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
    
    if not media_file_id and not text:
        bot.reply_to(message, "❌ Nothing to post.\n\nHow to use:\n• Send photo/video + /post in caption\n• Or reply to media with /post + text")
        return
    
    new_post = {
        "text": text or "Free Tips",
        "media": media_file_id,
        "media_type": media_type,
        "timestamp": datetime.now()
    }
    
    today_free_games.append(new_post)
    
    bot.reply_to(message, f"✅ Post saved! Today's total: **{len(today_free_games)}** posts", parse_mode="Markdown")
    
    try:
        if media_file_id and media_type == "photo":
            bot.send_photo(message.chat.id, media_file_id, caption=text)
        elif media_file_id and media_type == "video":
            bot.send_video(message.chat.id, media_file_id, caption=text)
        else:
            bot.send_message(message.chat.id, text)
    except:
        pass

# ====================== START ======================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    all_users.add(user_id)
    daily_reset_check()
    
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer = int(args[1][4:])
            if referrer != user_id and referrer in users_data:
                reset_invites_if_expired(referrer)
                users_data[referrer]["invites"] += 1
                users_data[referrer]["last_referral_date"] = datetime.now()
                
                if users_data[referrer]["invites"] >= 5 and not users_data[referrer].get("access_granted_date"):
                    bot.send_message(referrer, "🎉 Congratulations! You now have 7 days access!")
                
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
            if today_free_games:
                bot.send_message(message.chat.id, f"🎮 **Today's Free Games** ({len(today_free_games)} posts)", parse_mode="Markdown")
                for post in today_free_games:
                    media = post.get("media")
                    media_type = post.get("media_type")
                    caption = post.get("text", "")
                    try:
                        if media and media_type == "photo":
                            bot.send_photo(message.chat.id, media, caption=caption)
                        elif media and media_type == "video":
                            bot.send_video(message.chat.id, media, caption=caption)
                        else:
                            bot.send_message(message.chat.id, caption)
                        time.sleep(0.4)
                    except Exception as e:
                        logger.warning(f"Failed to send post: {e}")
            else:
                bot.send_message(message.chat.id, "No free games posted today yet.")
        else:
            invites = users_data.get(user_id, {}).get("invites", 0)
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("🔗 Share to Friends", callback_data=f"share_ref_{user_id}"))
            bot.send_message(
                message.chat.id,
                f"❌ Access required: **5 Friends**\n\n"
                f"Current invites: `{Friends}/5`\n\n"
                "Invite more friends to get access:",
                parse_mode="Markdown",
                reply_markup=markup
            )
    
    elif text == "📜 Previous Free Games":
        daily_reset_check()
        if free_games_posts or today_free_games:
            bot.send_message(message.chat.id, "📜 **Previous Free Games**", parse_mode="Markdown")
            if today_free_games:
                bot.send_message(message.chat.id, "→ **Today's Posts**", parse_mode="Markdown")
                for post in today_free_games:
                    media = post.get("media")
                    media_type = post.get("media_type")
                    caption = post.get("text", "")
                    try:
                        if media and media_type == "photo":
                            bot.send_photo(message.chat.id, media, caption=caption)
                        elif media and media_type == "video":
                            bot.send_video(message.chat.id, media, caption=caption)
                        else:
                            bot.send_message(message.chat.id, caption)
                        time.sleep(0.4)
                    except:
                        pass
            if free_games_posts:
                bot.send_message(message.chat.id, "→ **Older Days**", parse_mode="Markdown")
                for day_posts in reversed(free_games_posts[-10:]):
                    for post in day_posts:
                        media = post.get("media")
                        media_type = post.get("media_type")
                        caption = post.get("text", "")
                        try:
                            if media and media_type == "photo":
                                bot.send_photo(message.chat.id, media, caption=caption)
                            elif media and media_type == "video":
                                bot.send_video(message.chat.id, media, caption=caption)
                            else:
                                bot.send_message(message.chat.id, caption)
                            time.sleep(0.4)
                        except:
                            pass
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
        bot.send_message(message.chat.id, "💎 Want VIP Service?\nContact me for premium access.", reply_markup=markup)

# ====================== CALLBACKS ======================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    if not anti_spam(user_id, cooldown=2):
        bot.answer_callback_query(call.id, "⏳ Please wait...", show_alert=True)
        return

    daily_reset_check()

    if data == "check_channel":
        if is_member_of_channel(user_id) or is_admin(user_id):
            if not is_admin(user_id):
                if user_id not in users_data:
                    users_data[user_id] = {"joined_channel": False, "invites": 0, "last_referral_date": None, "access_granted_date": None}
                users_data[user_id]["joined_channel"] = True

            try:
                bot.edit_message_text(
                    "✅ You have successfully joined the channel!\n\nMain menu unlocked.",
                    call.message.chat.id, call.message.message_id,
                    reply_markup=None
                )
            except:
                pass

            bot.send_message(
                call.message.chat.id,
                "Use the buttons below:",
                reply_markup=get_persistent_keyboard()
            )
            all_users.add(user_id)
            bot.answer_callback_query(call.id, "✅ Access granted!")
        else:
            bot.answer_callback_query(call.id, "❌ Please Join the private channel, if you send request than wait for Approval.", show_alert=True)

    elif data.startswith("share_ref_"):
        try:
            target_user_id = int(data.split("_")[-1])
            ref_link = get_referral_link(target_user_id)
            bot.answer_callback_query(call.id, "✅ Referral link ready")
            bot.send_message(
                call.message.chat.id,
                f"🔗 **Your Personal Referral Link**\n\n"
                f"{ref_link}\n\n"
                "Long-press → Copy or Forward to friends.\nEach new user = +1 invite!",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Share error: {e}")
            bot.answer_callback_query(call.id, "❌ Error", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "Unknown action")

# ====================== BOT START ======================
if __name__ == "__main__":
    logger.info("🤖 Free Tips Bot starting...")
    
    try:
        bot.delete_webhook(drop_pending_updates=True)
        time.sleep(2)
    except:
        pass
    
    logger.info("🚀 Bot started with approval handler!")
    
    while True:
        try:
            # Must include 'chat_member' to receive approval events
            bot.infinity_polling(
                none_stop=True, 
                interval=1, 
                timeout=30,
                allowed_updates=['message', 'callback_query', 'chat_member']
            )
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(10)
