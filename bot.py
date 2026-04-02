import telebot
import os
import time
import logging
from datetime import datetime, timedelta
from telebot import types
from collections import defaultdict
import psycopg2
from psycopg2.extras import DictCursor

# ====================== CONFIG ======================
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    TOKEN = "8493101678:AAE7SAk1bIIfQyk7OnWS8e2uAWYrdF6f88k"   # Remove after testing

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required!")

# ================== SETTINGS ==================
CHANNEL_ID = "-1001775169065"
CHANNEL_INVITE_LINK = "https://t.me/+NzZ2mbPo9_02MDk8"
ADMIN_ID = 8258407224
VIP_USERNAME = "Antonio_Gomez_01"

bot = telebot.TeleBot(TOKEN)

# ====================== LOGGING ======================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ====================== DATABASE ======================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor, connect_timeout=10)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            joined_channel BOOLEAN DEFAULT FALSE,
            invites INTEGER DEFAULT 0,
            last_referral_date TIMESTAMP,
            access_granted_date TIMESTAMP
        );""")
        
        cur.execute("""CREATE TABLE IF NOT EXISTS today_free_games (
            id SERIAL PRIMARY KEY, media TEXT, media_type TEXT, text TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""")
        
        cur.execute("""CREATE TABLE IF NOT EXISTS free_games_archive (
            id SERIAL PRIMARY KEY, day DATE, posts JSONB, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""")
        
        cur.execute("""CREATE TABLE IF NOT EXISTS won_tickets (
            id SERIAL PRIMARY KEY,
            media TEXT,
            media_type TEXT,
            text TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""")
        
        conn.commit()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"DB Init Error: {e}")
    finally:
        cur.close()
        conn.close()

def load_data():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM users")
        users_data = {row['user_id']: dict(row) for row in cur.fetchall()}

        cur.execute("SELECT media, media_type, text FROM today_free_games ORDER BY id")
        today_free_games = [dict(row) for row in cur.fetchall()]

        cur.execute("SELECT posts FROM free_games_archive ORDER BY day DESC LIMIT 30")
        free_games_posts = [row['posts'] for row in cur.fetchall()]

        cur.execute("""
            SELECT media, media_type, text 
            FROM won_tickets 
            WHERE expires_at > NOW() 
            ORDER BY created_at DESC
        """)
        won_tickets = [dict(row) for row in cur.fetchall()]

        return users_data, today_free_games, free_games_posts, won_tickets
    finally:
        cur.close()
        conn.close()

def save_user(user_id, data):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (user_id, joined_channel, invites, last_referral_date, access_granted_date)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                joined_channel = EXCLUDED.joined_channel,
                invites = EXCLUDED.invites,
                last_referral_date = EXCLUDED.last_referral_date,
                access_granted_date = EXCLUDED.access_granted_date
        """, (user_id, data.get("joined_channel"), data.get("invites"),
              data.get("last_referral_date"), data.get("access_granted_date")))
        conn.commit()
    finally:
        cur.close()
        conn.close()

# ====================== INITIALIZE ======================
init_db()
users_data, today_free_games, free_games_posts, won_tickets = load_data()
last_daily_reset = datetime.now().date()
last_action_time = defaultdict(lambda: datetime.min)

bot_me = bot.get_me()
BOT_USERNAME = bot_me.username if bot_me else None

# ====================== HELPERS ======================
def get_user_referrals(user_id):
    if user_id in users_data:
        return users_data[user_id].get("invites", 0)
    return 0

def is_member_of_channel(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

def anti_spam(user_id, cooldown=3):
    now = datetime.now()
    if (now - last_action_time[user_id]) < timedelta(seconds=cooldown):
        return False
    last_action_time[user_id] = now
    return True

def clean_expired_won_tickets():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM won_tickets WHERE expires_at <= NOW()")
        conn.commit()
    finally:
        cur.close()
        conn.close()

def daily_reset_check():
    global last_daily_reset
    today = datetime.now().date()
    if today > last_daily_reset:
        if today_free_games:
            conn = get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("INSERT INTO free_games_archive (day, posts) VALUES (%s, %s::jsonb)", 
                           (last_daily_reset, today_free_games))
                conn.commit()
                free_games_posts.insert(0, today_free_games[:])
                if len(free_games_posts) > 30:
                    free_games_posts.pop()
            finally:
                cur.close()
                conn.close()
            bot.send_message(ADMIN_ID, f"✅ Daily reset completed. {len(today_free_games)} posts archived.")
        today_free_games.clear()
        last_daily_reset = today

def get_persistent_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2, is_persistent=True)
    markup.add("🎮 Today's Free Games", "📜 Previous Free Games")
    markup.add("🏆 Referral Leaderboard", "✅ Won Tickets")
    markup.add("💎 VIP Service 💯")
    return markup

# ====================== CHANNEL HANDLER ======================
@bot.chat_member_handler()
def handle_channel_update(update):
    try:
        if str(update.chat.id) != CHANNEL_ID:
            return
        user = update.new_chat_member.user
        user_id = user.id
        status = update.new_chat_member.status

        if status in ["member", "administrator", "creator"]:
            if user_id not in users_data:
                users_data[user_id] = {"joined_channel": True, "invites": 0, "last_referral_date": None, "access_granted_date": None}
            else:
                users_data[user_id]["joined_channel"] = True
            save_user(user_id, users_data[user_id])

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ I Have Joined", callback_data="check_channel"))
            bot.send_message(user_id, f"Hello 👋 {user.first_name}, you have been Approved!\n\nClick 👉 I have Joined ☝️", reply_markup=markup)

        elif status in ["left", "kicked"]:
            if user_id in users_data:
                users_data[user_id]["joined_channel"] = False
                save_user(user_id, users_data[user_id])
                bot.send_message(user_id, "❌ You left the channel. Your access has been revoked.\nPlease rejoin the channel to continue.")
    except Exception as e:
        logger.error(f"Channel handler error: {e}")

# ====================== COMMANDS ======================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    daily_reset_check()
    access = check_access(user_id)

    # Referral handling
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1][3:])
            if referrer_id != user_id and referrer_id in users_data:
                data = users_data[referrer_id]
                data["invites"] += 1
                data["last_referral_date"] = datetime.now()
                save_user(referrer_id, data)
                bot.send_message(referrer_id, f"🎉 New referral! Total invites: {data['invites']}/5")
        except:
            pass

    if access == "channel":
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("✅ Join Private Channel", url=CHANNEL_INVITE_LINK))
        markup.add(types.InlineKeyboardButton("🔄 I Have Joined", callback_data="check_channel"))
        bot.send_message(message.chat.id, "👋 Welcome!\nYou must join our private channel first.", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "✅ Welcome back! Use the menu below.", reply_markup=get_persistent_keyboard())

@@bot.message_handler(commands=['post'], func=lambda m: m.from_user.id == ADMIN_ID)
def post_free_games(message):
    try:
        # Get caption if provided
        text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else ""

        media = None
        media_type = None

        if message.photo:
            media = message.photo[-1].file_id
            media_type = "photo"
        elif message.video:
            media = message.video.file_id
            media_type = "video"

        if not media:
            bot.reply_to(message, "❌ Please **attach a photo or video** and then reply to it with:\n`/post Your caption here`")
            return

        today_free_games.append({"media": media, "media_type": media_type, "text": text})
        
        bot.reply_to(message, f"✅ Successfully added **{media_type}** to Today's Free Games!\nTotal posts today: {len(today_free_games)}")
        
    except Exception as e:
        bot.reply_to(message, "❌ Error. Send a photo/video first, then reply with /post <caption>")

@bot.message_handler(commands=['win'], func=lambda m: m.from_user.id == ADMIN_ID)
def post_won_ticket(message):
    try:
        text = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else "Winning Ticket"

        media = None
        media_type = None

        if message.photo:
            media = message.photo[-1].file_id
            media_type = "photo"
        elif message.video:
            media = message.video.file_id
            media_type = "video"

        if not media:
            bot.reply_to(message, "❌ Please **attach a photo or video** and then reply to it with:\n`/win Your caption here`")
            return

        expires_at = datetime.now() + timedelta(days=30)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO won_tickets (media, media_type, text, expires_at) VALUES (%s, %s, %s, %s)",
                   (media, media_type, text, expires_at))
        conn.commit()
        cur.close()
        conn.close()

        won_tickets.insert(0, {"media": media, "media_type": media_type, "text": text})
        bot.reply_to(message, f"✅ Winning ticket ({media_type}) posted successfully! Expires in 30 days.")
        
    except Exception as e:
        bot.reply_to(message, "❌ Error. Send a photo/video first, then reply with /win <caption>")

# ====================== KEYBOARD HANDLER ======================
@bot.message_handler(content_types=['text'])
def handle_keyboard(message):
    user_id = message.from_user.id
    text = message.text.strip()
    daily_reset_check()
    clean_expired_won_tickets()

    if not anti_spam(user_id):
        return

    access = check_access(user_id)

    if text == "🎮 Today's Free Games":
        if access == "full":
            if today_free_games:
                bot.send_message(message.chat.id, f"🎮 **Today's Free Games** ({len(today_free_games)})", parse_mode="Markdown")
                for post in today_free_games:
                    try:
                        if post.get("media_type") == "photo" and post.get("media"):
                            bot.send_photo(message.chat.id, post["media"], caption=post.get("text"))
                        elif post.get("media_type") == "video" and post.get("media"):
                            bot.send_video(message.chat.id, post["media"], caption=post.get("text"))
                        else:
                            bot.send_message(message.chat.id, post.get("text") or "🎮 Free Game")
                        time.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Failed to send today's game: {e}")
                        bot.send_message(message.chat.id, "⚠️ Could not display this post.")
            else:
                bot.send_message(message.chat.id, "No free games today yet.")
        
        else:
            current_referrals = get_user_referrals(user_id)
            needed = max(5 - current_referrals, 1)

            message_text = (
                "❌ You don't have full access yet.\n\n"
                "You need **5 friends** to get access to Free Games.\n\n"
                f"👥 Friends referred so far: **{current_referrals}**\n"
                f"🔜 You still need: **{needed}** more friend{'' if needed == 1 else 's'}"
            )

            markup = types.InlineKeyboardMarkup(row_width=1)
            share_button = types.InlineKeyboardButton(
                text="🔗 Share with Friends",
                url=f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}?start=ref{user_id}&text=Join%20me%20and%20unlock%20Free%20Games%20together!%20%F0%9F%8E%AE"
            )
            markup.add(share_button)

            bot.send_message(message.chat.id, message_text, parse_mode="Markdown", reply_markup=markup)

    elif text == "✅ Won Tickets":
        if won_tickets:
            bot.send_message(message.chat.id, f"✅ **Won Tickets** ({len(won_tickets)} active)", parse_mode="Markdown")
            for post in won_tickets:
                try:
                    if post.get("media_type") == "photo" and post.get("media"):
                        bot.send_photo(message.chat.id, post["media"], caption=post.get("text", "Winning Ticket"))
                    elif post.get("media_type") == "video" and post.get("media"):
                        bot.send_video(message.chat.id, post["media"], caption=post.get("text", "Winning Ticket"))
                    else:
                        bot.send_message(message.chat.id, post.get("text", "Winning Ticket"))
                    time.sleep(0.5)
                except Exception as e:
                    logger.error(f"Failed to send won ticket: {e}")
                    bot.send_message(message.chat.id, "⚠️ Could not display this ticket.")
        else:
            bot.send_message(message.chat.id, "No winning tickets yet.")

    elif text == "📜 Previous Free Games":
        if free_games_posts:
            bot.send_message(message.chat.id, "📜 **Previous Free Games**", parse_mode="Markdown")
            for day_posts in free_games_posts[:5]:
                for post in day_posts:
                    try:
                        if post.get("media_type") == "photo" and post.get("media"):
                            bot.send_photo(message.chat.id, post["media"], caption=post.get("text"))
                        elif post.get("media_type") == "video" and post.get("media"):
                            bot.send_video(message.chat.id, post["media"], caption=post.get("text"))
                        else:
                            bot.send_message(message.chat.id, post.get("text"))
                        time.sleep(0.4)
                    except:
                        pass
        else:
            bot.send_message(message.chat.id, "No previous games yet.")

    elif text == "🏆 Referral Leaderboard":
        sorted_users = sorted(users_data.items(), key=lambda x: x[1].get("invites", 0), reverse=True)
        lb = "🏆 **Top Referrers**\n\n"
        for i, (uid, data) in enumerate(sorted_users[:15], 1):
            lb += f"{i}. User `{uid}` — **{data.get('invites', 0)}** invites\n"
        bot.send_message(message.chat.id, lb, parse_mode="Markdown")

    elif text == "💎 VIP Service 💯":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💬 Contact Admin", url=f"https://t.me/{VIP_USERNAME}"))
        bot.send_message(message.chat.id, "💎 Want VIP Service?\nContact Admin for premium access.", reply_markup=markup)

# ====================== CALLBACKS ======================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    if call.data == "check_channel":
        if is_member_of_channel(user_id):
            users_data[user_id]["joined_channel"] = True
            save_user(user_id, users_data[user_id])
            bot.send_message(call.message.chat.id, "✅ Access granted!", reply_markup=get_persistent_keyboard())
        else:
            bot.answer_callback_query(call.id, "❌ You have not joined yet.", show_alert=True)

# ====================== ACCESS CHECK ======================
def check_access(user_id):
    if user_id == ADMIN_ID:
        return "full"
    if user_id not in users_data:
        users_data[user_id] = {"joined_channel": False, "invites": 0, "last_referral_date": None, "access_granted_date": None}
        save_user(user_id, users_data[user_id])
    data = users_data[user_id]
    if not data.get("joined_channel"):
        return "channel"
    if data.get("access_granted_date"):
        if (datetime.now() - data["access_granted_date"]) <= timedelta(days=7):
            return "full"
        else:
            data["invites"] = 0
            data["access_granted_date"] = None
            save_user(user_id, data)
    if data["invites"] >= 5:
        data["access_granted_date"] = datetime.now()
        save_user(user_id, data)
        return "full"
    return "invites"

# ====================== BOT START ======================
if __name__ == "__main__":
    logger.info("🤖 Bot starting with all features...")
    try:
        bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook cleared successfully")
        
        bot.infinity_polling(none_stop=True, 
                            allowed_updates=['message', 'callback_query', 'chat_member'],
                            timeout=30,
                            long_polling_timeout=30)
    except Exception as e:
        logger.error(f"Critical error: {e}")
