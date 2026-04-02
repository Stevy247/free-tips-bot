import telebot
import os
import time
import logging
from datetime import datetime, timedelta
from telebot import types
from collections import defaultdict
import psycopg2
from psycopg2.extras import DictCursor
import json

# ====================== CONFIG ======================
TOKEN = os.getenv("TOKEN")

# Temporary for testing (remove or use env var on Railway)
if not TOKEN:
    TOKEN = "8493101678:AAE7SAk1bIIfQyk7OnWS8e2uAWYrdF6f88k"

print("TOKEN loaded:", bool(TOKEN))
if not TOKEN:
    raise ValueError("No TOKEN provided")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required!")

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

# ====================== POSTGRES CONNECTION ======================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                joined_channel BOOLEAN DEFAULT FALSE,
                invites INTEGER DEFAULT 0,
                last_referral_date TIMESTAMP,
                access_granted_date TIMESTAMP
            );
        """)
        
        # Free games archive
        cur.execute("""
            CREATE TABLE IF NOT EXISTS free_games_archive (
                id SERIAL PRIMARY KEY,
                day DATE,
                posts JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Today's free games (simple)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS today_free_games (
                id SERIAL PRIMARY KEY,
                media TEXT,
                media_type TEXT,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        conn.commit()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"Database init error: {e}")
    finally:
        cur.close()
        conn.close()

# Load data from DB
def load_data():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Load users
        cur.execute("SELECT * FROM users")
        users = {}
        for row in cur.fetchall():
            users[row['user_id']] = {
                "joined_channel": row['joined_channel'],
                "invites": row['invites'],
                "last_referral_date": row['last_referral_date'],
                "access_granted_date": row['access_granted_date']
            }
        
        # Load today's games
        cur.execute("SELECT media, media_type, text FROM today_free_games ORDER BY id")
        today_games = [dict(row) for row in cur.fetchall()]
        
        # Load archive
        cur.execute("SELECT posts FROM free_games_archive ORDER BY day DESC LIMIT 30")
        archive = [row['posts'] for row in cur.fetchall()]
        
        return users, today_games, archive
    finally:
        cur.close()
        conn.close()

# Save user data
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
        """, (
            user_id,
            data.get("joined_channel", False),
            data.get("invites", 0),
            data.get("last_referral_date"),
            data.get("access_granted_date")
        ))
        conn.commit()
    finally:
        cur.close()
        conn.close()

# ====================== INITIALIZE ======================
init_db()
users_data, today_free_games, free_games_posts = load_data()
all_users = set(users_data.keys())
last_daily_reset = datetime.now().date()
last_action_time = defaultdict(lambda: datetime.min)

bot_me = bot.get_me()
BOT_USERNAME = bot_me.username if bot_me and bot_me.username else None
print("🔍 Current bot username:", BOT_USERNAME)

# ====================== HELPER FUNCTIONS ======================
def get_referral_link(user_id: int) -> str:
    if not BOT_USERNAME:
        return "Bot username not set!"
    return f"https://t.me/{BOT_USERNAME}?start=ref{user_id}"

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
        save_user(user_id, data)

# (Rest of your functions like check_access, is_member_of_channel, etc. remain almost the same)

def check_access(user_id: int) -> str:
    if user_id == ADMIN_ID:
        return "full"

    reset_invites_if_expired(user_id)

    if user_id not in users_data:
        users_data[user_id] = {
            "joined_channel": False,
            "invites": 0,
            "last_referral_date": None,
            "access_granted_date": None
        }
        save_user(user_id, users_data[user_id])

    data = users_data[user_id]

    if not is_member_of_channel(user_id):
        data["joined_channel"] = False
        save_user(user_id, data)

    if not data["joined_channel"]:
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

# Keep your other functions (anti_spam, daily_reset_check, etc.)
# Just make sure to call save_user() whenever you modify users_data[user_id]

# ====================== BOT START ======================
if __name__ == "__main__":
    logger.info("🤖 Free Tips AI Bot starting with PostgreSQL...")
    try:
        bot.delete_webhook(drop_pending_updates=True)
    except:
        pass

    logger.info("🚀 Bot started successfully!")
    
    while True:
        try:
            bot.infinity_polling(none_stop=True, interval=1, timeout=30,
                                allowed_updates=['message', 'callback_query', 'chat_member'])
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(10)
