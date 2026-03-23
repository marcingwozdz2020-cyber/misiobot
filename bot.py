import os
import logging
import sqlite3
import feedparser
import telebot
from datetime import datetime
from openai import OpenAI
from contextlib import contextmanager
import time

# --- Konfiguracja ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Pobieranie tokenów z env
TELEGRAM_TOKEN = os.environ.get("telegram_token")
OPENAI_API_KEY = os.environ.get("openai_api_key")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Brakuje zmiennych środowiskowych: telegram_token lub openai_api_key")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Baza danych ---
DATABASE_PATH = "tweets.db"
pending_tweets = {}

@contextmanager
def get_db_connection():
    """Context manager dla bazy danych."""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """Inicjalizuje bazę danych."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tweets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        logger.info("Baza danych zainicjalizowana")

def get_latest_news(limit=3):
    """Pobiera najnowsze nagłówki z Google News."""
    try:
        url = "https://news.google.com/rss?hl=pl&gl=PL&ceid=PL:pl"
        feed = feedparser.parse(url, timeout=5)
        
        if not feed.entries:
            return "Aktualna sytuacja polityczna"
        
        titles = [entry.title for entry in feed.entries[:limit]]
        return "\n".join(titles)[:300]  # Limit tekstu
    except Exception as e:
        logger.warning(f"Nie udało się pobrać newsów: {e}")
        return "Aktualna sytuacja polityczna"

def generate_ai_tweet(topic):
    """Generuje tweet przy pomocy OpenAI."""
    try:
        news_context = get_latest_news()
        
        prompt = f"""Jesteś ekspertem od marketingu politycznego. 
Na temat: {topic}

Napisz KRÓTKI, angażujący tweet w języku polskim (MAX 240 znaków).
Nie używaj hashtagów. Bądź konkretny i zaczepny."""
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.8,
            timeout=30
        )
        
        tweet = response.choices[0].message.content.strip()
        logger.info(f"Tweet wygenerowany: {topic}")
        return tweet
    except Exception as e:
        logger.error(f"Błąd OpenAI: {e}")
        return f"❌ Błąd API: {str(e)[:50]}"

def save_tweet(tweet):
    """Zapisuje tweet do bazy."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO tweets (tweet) VALUES (?)", (tweet,))
            conn.commit()
            logger.info("Tweet zapisany")
            return True
    except Exception as e:
        logger.error(f"Błąd zapisu: {e}")
        return False

def get_all_tweets(limit=10):
    """Pobiera tweety z bazy."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, tweet, created_at FROM tweets ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"Błąd odczytu: {e}")
        return []

def delete_tweet(tweet_id):
    """Usuwa tweet."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tweets WHERE id = ?", (tweet_id,))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Błąd usunięcia: {e}")
        return False

# --- HANDLERY KOMEND ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "🤖 <b>Bot AI aktywny!</b>\n\nWpisz:\n/generate [temat] - Wygeneruj tweet\n/help - Pomoc")

@bot.message_handler(commands=['generate'])
def handle_generate(message):
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "polityka"
        
        status_msg = bot.send_message(message.chat.id, "⏳ Myślę...")
        
        tweet = generate_ai_tweet(topic)
        pending_tweets[message.chat.id] = tweet
        
        bot.delete_message(message.chat.id, status_msg.message_id)
        bot.send_message(message.chat.id, f"<b>🤖 AI wygenerowało:</b>\n\n{tweet}\n\nWpisz /save aby zapisać")
        
    except Exception as e:
        logger.error(f"Błąd: {e}")
        bot.reply_to(message, f"❌ Błąd: {str(e)[:100]}")

@bot.message_handler(commands=['save'])
def handle_save(message):
    tweet = pending_tweets.get(message.chat.id)
    if tweet:
        if save_tweet(tweet):
            bot.reply_to(message, "✅ <b>Zapisano w bazie!</b>")
            del pending_tweets[message.chat.id]
        else:
            bot.reply_to(message, "❌ Błąd zapisu")
    else:
        bot.reply_to(message, "⚠️ Brak tweeta. Wpisz /generate [temat]")

@bot.message_handler(commands=['list'])
def handle_list(message):
    tweets = get_all_tweets(10)
    if not tweets:
        bot.reply_to(message, "📋 Brak zapisanych tweetów")
    else:
        response = "<b>📋 Zapisane tweety:</b>\n\n"
        for tweet_id, text, created_at in tweets:
            response += f"<b>ID: {tweet_id}</b>\n{text}\n\n"
        bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['delete'])
def handle_delete(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Użycie: /delete <id>")
            return
        tweet_id = int(args[1])
        if delete_tweet(tweet_id):
            bot.reply_to(message, "✅ Usunięto!")
        else:
            bot.reply_to(message, "❌ Nie znaleziono")
    except:
        bot.reply_to(message, "❌ ID musi być liczbą")

@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = """<b>🤖 Dostępne komendy:</b>

/start - Start
/generate [temat] - Wygeneruj tweet
/save - Zapisz tweet
/list - Wyświetl tweety
/delete [id] - Usuń tweet
/help - Pomoc"""
    bot.reply_to(message, help_text)

if __name__ == "__main__":
    init_database()
    logger.info("Bot AI STARTED...")
    try:
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Krytyczny błąd: {e}")
