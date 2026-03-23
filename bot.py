import os
import logging
import sqlite3
import feedparser
import telebot
from datetime import datetime
from openai import OpenAI
from contextlib import contextmanager

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

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Baza danych ---
DATABASE_PATH = "tweets.db"
pending_tweets = {}

# Wiadomości
MESSAGES = {
    "start": "🤖 Bot aktywny! Wpisz /generate [temat], aby stworzyć tweet na bazie newsów.",
    "generated": "🤖 **AI wygenerowało:**\n\n{tweet}\n\nUżyj /save aby zapisać do bazy.",
    "saved": "✅ Zapisano w bazie!",
    "no_tweet": "Brak tweeta do zapisu. Najpierw /generate.",
    "list_empty": "Brak zapisanych tweetów.",
    "list_header": "📋 Zapisane tweety:",
    "deleted": "✅ Tweet usunięty!",
    "error_openai": "Błąd podczas generowania przez AI: {error}",
    "error_db": "Błąd bazy danych: {error}",
    "started": "Bot AI wystartował..."
}

# --- Context Manager dla bazy danych ---
@contextmanager
def get_db_connection():
    """Context manager dla bezpiecznego połączenia z bazą danych."""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()

# --- Inicjalizacja bazy danych ---
def init_database():
    """Inicjalizuje bazę danych i tworzy tabele."""
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

# --- Logika Pobierania i Generowania ---
def get_latest_news(limit: int = 5) -> str:
    """
    Pobiera najnowsze nagłówki z Google News.
    
    Args:
        limit: Liczba nagłówków do pobrania (domyślnie 5)
    
    Returns:
        String z nagłówkami oddzielonymi znakami nowego wiersza
    """
    try:
        url = "https://news.google.com/rss?hl=pl&gl=PL&ceid=PL:pl"
        feed = feedparser.parse(url)
        
        if not feed.entries:
            logger.warning("Brak wpisów w RSS")
            return "Brak bieżących nagłówków w RSS."
        
        titles = [entry.title for entry in feed.entries[:limit]]
        return "\n".join(titles)
    except Exception as e:
        logger.error(f"Błąd pobierania newsów: {e}")
        return "Nie udało się pobrać newsów."

def generate_ai_tweet(topic: str) -> str:
    """
    Generuje tweet przy pomocy OpenAI na podstawie podanego tematu i bieżących newsów.
    
    Args:
        topic: Temat tweeta
    
    Returns:
        Wygenerowany tweet
    """
    try:
        news_context = get_latest_news()
        
        prompt = f"""Jesteś ekspertem od marketingu politycznego. Na podstawie poniższych newsów:\n{news_context}\n\nNapisz krótki, angażujący tweet na temat: {topic}. \nTweet musi być w języku polskim, zawierać max 240 znaków i pasować do stylu Twittera.\nNie używaj hashtagów."""
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.7
        )
        
        tweet = response.choices[0].message.content.strip()
        logger.info(f"Tweet wygenerowany na temat: {topic}")
        return tweet
    except Exception as e:
        logger.error(f"Błąd OpenAI: {e}")
        return MESSAGES["error_openai"].format(error=str(e))

# --- Operacje na bazie danych ---
def save_tweet(tweet: str) -> bool:
    """Zapisuje tweet do bazy danych."""
    
    Args:
        tweet: Tekst tweeta do zapisania
    
    Returns:
        True jeśli udało się zapisać, False w przypadku błędu
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tweets (tweet, created_at) VALUES (?, ?)"
                , (tweet, datetime.now())
            )
            conn.commit()
            logger.info(f"Tweet zapisany do bazy")
            return True
    except Exception as e:
        logger.error(f"Błąd zapisu do bazy: {e}")
        return False

def get_all_tweets(limit: int = 10) -> list:
    """Pobiera wszystkie tweety z bazy danych."""
    
    Args:
        limit: Maksymalna liczba tweetów do pobrania
    
    Returns:
        Lista tweetów jako krotki (id, tweet, created_at)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, tweet, created_at FROM tweets ORDER BY created_at DESC LIMIT ?"
                , (limit,)
            )
            tweets = cursor.fetchall()
            return tweets
    except Exception as e:
        logger.error(f"Błąd odczytu z bazy: {e}")
        return []

def delete_tweet(tweet_id: int) -> bool:
    """Usuwa tweet z bazy danych."""
    
    Args:
        tweet_id: ID tweeta do usunięcia
    
    Returns:
        True jeśli udało się usunąć, False w przypadku błędu
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tweets WHERE id = ?", (tweet_id,))
            conn.commit()
            logger.info(f"Tweet ID {tweet_id} usunięty")
            return True
    except Exception as e:
        logger.error(f"Błąd usunięcia tweeta: {e}")
        return False

# --- Handlery ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    """Obsługuje komendę /start."""
    bot.reply_to(message, MESSAGES["start"])

@bot.message_handler(commands=['generate'])
def handle_generate(message):
    """Obsługuje komendę /generate - generuje nowy tweet."""
    try:
        args = message.text.split(maxsplit=1)
        topic = args[1] if len(args) > 1 else "aktualna sytuacja polityczna"
        
        bot.send_chat_action(message.chat.id, 'typing')
        tweet = generate_ai_tweet(topic)
        
        pending_tweets[message.chat.id] = tweet
        bot.reply_to(message, MESSAGES["generated"].format(tweet=tweet))
        logger.info(f"User {message.chat.id} wygenerował tweet")
    except Exception as e:
        logger.error(f"Błąd w /generate: {e}")
        bot.reply_to(message, f"❌ Błąd: {str(e)}")

@bot.message_handler(commands=['save'])
def handle_save(message):
    """Obsługuje komendę /save - zapisuje pending tweet do bazy."""
    try:
        tweet = pending_tweets.get(message.chat.id)
        if tweet:
            if save_tweet(tweet):
                bot.reply_to(message, MESSAGES["saved"])
                del pending_tweets[message.chat.id]
            else:
                bot.reply_to(message, MESSAGES["error_db"].format(error="Nie udało się zapisać"))
        else:
            bot.reply_to(message, MESSAGES["no_tweet"])
    except Exception as e:
        logger.error(f"Błąd w /save: {e}")
        bot.reply_to(message, f"❌ Błąd: {str(e)}")

@bot.message_handler(commands=['list'])
def handle_list(message):
    """Obsługuje komendę /list - wyświetla ostatnie tweety."""
    try:
        tweets = get_all_tweets(limit=10)
        if not tweets:
            bot.reply_to(message, MESSAGES["list_empty"])
        else:
            response = MESSAGES["list_header"] + "\n\n"
            for tweet_id, tweet_text, created_at in tweets:
                response += f"**ID: {tweet_id}** ({created_at})\n{tweet_text}\n\n"
            bot.reply_to(message, response)
            logger.info(f"User {message.chat.id} wyświetlił listę tweetów")
    except Exception as e:
        logger.error(f"Błąd w /list: {e}")
        bot.reply_to(message, f"❌ Błąd: {str(e)}")

@bot.message_handler(commands=['delete'])
def handle_delete(message):
    """Obsługuje komendę /delete - usuwa tweet po ID."""
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(message, "Użycie: /delete <id_tweeta>")
            return
        
        tweet_id = int(args[1])
        if delete_tweet(tweet_id):
            bot.reply_to(message, MESSAGES["deleted"])
        else:
            bot.reply_to(message, "❌ Nie udało się usunąć tweeta")
            logger.info(f"User {message.chat.id} usunął tweet ID {tweet_id}")
    except ValueError:
        bot.reply_to(message, "❌ ID musi być liczbą")
    except Exception as e:
        logger.error(f"Błąd w /delete: {e}")
        bot.reply_to(message, f"❌ Błąd: {str(e)}")

@bot.message_handler(commands=['help'])
def handle_help(message):
    """Obsługuje komendę /help - wyświetla dostępne komendy."""
    help_text = """
🤖 Dostępne komendy:
/start - Uruchamia bota
/generate [temat] - Generuje nowy tweet
/save - Zapisuje ostatnio wygenerowany tweet
/list - Wyświetla ostatnie tweety
/delete <id> - Usuwa tweet po ID
/help - Wyświetla tę wiadomość
    """
    bot.reply_to(message, help_text)

if __name__ == "__main__":
    init_database()
    logger.info(MESSAGES["started"])
    try:
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Błąd krytyczny: {e}")