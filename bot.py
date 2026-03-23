import os
import logging
import sqlite3
from datetime import datetime
import telebot
from textwrap import shorten

# ---------------------------------------
# Konfiguracja loggingu (poprawione basicConfig)
# ---------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------------------
# Telegram Bot - pobieranie tokena
# ---------------------------------------
telegram_token = os.environ.get("telegram_token")
if not telegram_token:
    logging.error("Brakuje zmiennej środowiskowej telegram_token!")
    # Dla testów możesz wpisać token bezpośrednio: bot = telebot.TeleBot("TWÓJ_TOKEN")
    raise ValueError("Brakuje zmiennej środowiskowej telegram_token")

bot = telebot.TeleBot(telegram_token)

# ---------------------------------------
# Baza danych (poprawione False i zapytania SQL)
# ---------------------------------------
conn = sqlite3.connect("tweets.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS tweets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tweet TEXT,
        created_at TIMESTAMP
    )
""")
conn.commit()

# ---------------------------------------
# Pamięć podręczna na propozycje
# ---------------------------------------
pending_tweets = {}

# ---------------------------------------
# Funkcje pomocnicze
# ---------------------------------------
def fetch_political_news():
    """Generator przykładowych nagłówków."""
    return [
        "Debata o bezpieczeństwie europejskim nabiera tempa",
        "Nowe napięcia na linii USA–Chiny",
        "Dyskusja o reformie sądownictwa w Polsce",
        "UE rozważa nowe sankcje gospodarcze",
        "Spotkanie przywódców w sprawie energii i obronności"
    ]

def generate_political_tweet(topic: str) -> str:
    headlines = fetch_political_news()
    # Łączymy nagłówki w treść
    body = "; ".join(headlines[:3])
    tweet = f"Polityka ({topic}): {body}"
    return shorten(tweet, width=260, placeholder="...")

def save_tweet(tweet: str):
    """Zapisuje tweet do bazy danych SQLite."""
    try:
        cursor.execute(
            "INSERT INTO tweets (tweet, created_at) VALUES (?, ?)",
            (tweet, datetime.now())
        )
        conn.commit()
        logging.info("Tweet pomyślnie zapisany w bazie.")
        return True
    except Exception as e:
        logging.error(f"Błąd zapisu do bazy: {e}")
        return False

# ---------------------------------------
# Handlery komend Telegrama
# ---------------------------------------

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = (
        "🤖 **Witaj w generatorze tweetów politycznych!**\n\n"
        "Komendy:\n"
        "/generate [temat] - Tworzy nową propozycję\n"
        "/save - Zapisuje ostatnią propozycję do bazy\n"
        "/list - Pokazuje ostatnie 5 zapisanych tweetów"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['generate'])
def handle_generate(message):
    # Pobieramy temat z tekstu po komendzie
    args = message.text.split(maxsplit=1)
    topic = args[1] if len(args) > 1 else "ogólny"
    
    tweet = generate_political_tweet(topic)
    pending_tweets[message.chat.id] = tweet
    
    response = f"📝 **Propozycja tweeta:**\n\n_{tweet}_\n\nZatwierdź wpisując /save"
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(commands=['save'])
def handle_save(message):
    tweet = pending_tweets.get(message.chat.id)
    if tweet:
        if save_tweet(tweet):
            del pending_tweets[message.chat.id]
            bot.reply_to(message, "✅ Tweet został zapisany w bazie danych!")
        else:
            bot.reply_to(message, "❌ Wystąpił błąd podczas zapisu.")
    else:
        bot.reply_to(message, "🤷 Nie masz żadnej propozycji do zapisania. Użyj najpierw /generate.")

@bot.message_handler(commands=['list'])
def handle_list(message):
    cursor.execute("SELECT tweet FROM tweets ORDER BY created_at DESC LIMIT 5")
    rows = cursor.fetchall()
    if rows:
        response = "🗄 **Ostatnie 5 zapisanych tweetów:**\n\n"
        for i, row in enumerate(rows, 1):
            response += f"{i}. {row[0]}\n\n"
        bot.send_message(message.chat.id, response)
    else:
        bot.reply_to(message, "Baza danych jest pusta.")

# ---------------------------------------
# Uruchomienie bota
# ---------------------------------------
if __name__ == "__main__":
    logging.info("Bot właśnie wystartował...")
    bot.infinity_polling()
