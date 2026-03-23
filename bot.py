import os
import logging
import sqlite3
from datetime import datetime
import telebot
from textwrap import shorten

# ---------------------------------------
# LOGGING
# ---------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ---------------------------------------
# TELEGRAM BOT
# ---------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    raise ValueError("Brakuje zmiennej środowiskowej TELEGRAM_TOKEN")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ---------------------------------------
# BAZA DANYCH
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
# PAMIĘĆ NA PROPOZYCJE
# ---------------------------------------
pending_tweets = {}

# ---------------------------------------
# GENERATOR POLITYCZNYCH TWEETÓW
# ---------------------------------------
def fetch_political_news():
    """
    Prosty generator nagłówków politycznych (PL + świat).
    Możesz później podmienić na prawdziwe API newsów.
    """
    return [
        "Debata o bezpieczeństwie europejskim nabiera tempa",
        "Nowe napięcia na linii USA–Chiny",
        "Dyskusja o reformie sądownictwa w Polsce",
        "UE rozważa nowe sankcje gospodarcze",
        "Spotkanie przywódców w sprawie energii i obronności"
    ]

def generate_political_tweet(topic: str) -> str:
    headlines = fetch_political_news()
    body = "; ".join(headlines[:3])
    tweet = f"Polityka ({topic}): {body}"
    return shorten(tweet, width=260, placeholder="...")

# ---------------------------------------
# ZAPIS DO BAZY
# ---------------------------------------
def save_tweet(tweet: str):
    cursor.execute(
        "INSERT INTO tweets (tweet, created_at) VALUES (?, ?)",
        (tweet, datetime.now())
    )
    conn.commit()
    logging.info(f"Zapisano tweet: {tweet}")

# ---------------------------------------
# KOMENDY TELEGRAM
# ---------------------------------------
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "Cześć! Jestem botem politycznym.\n"
        "Użyj:\n"
        "/stworz [temat] – wygeneruję propozycję tweeta\n"
        "/tak – zaakceptujesz\n"
        "/nie – odrzucisz\n"
        "Zatwierdzone tweety zapisuję w bazie SQLite."
    )

@bot.message_handler(commands=["stworz"])
def stworz(message):
    topic = message.text.replace("/stworz", "").strip()
    if not topic:
        topic = "polityka mieszana"

    generated = generate_political_tweet(topic)
    pending_tweets[message.chat.id] = generated

    bot.reply_to(
        message,
        f"Propozycja tweeta:\n\n{generated}\n\nAkceptujesz? /tak /nie"
    )

@bot.message_handler(commands=["tak"])
def accept(message):
    tweet = pending_tweets.get(message.chat.id)
    if not tweet:
        bot.reply_to(message, "Nie mam żadnej propozycji do akceptacji.")
        return

    save_tweet(tweet)
    bot.reply_to(message, f"Zatwierdzono i zapisano w bazie:\n\n{tweet}")
    pending_tweets.pop(message.chat.id, None)

@bot.message_handler(commands=["nie"])
def reject(message):
    if message.chat.id in pending_tweets:
        pending_tweets.pop(message.chat.id, None)
        bot.reply_to(message, "Odrzucono. Użyj /stworz, aby wygenerować nową propozycję.")
    else:
        bot.reply_to(message, "Nie mam żadnej propozycji do odrzucenia.")

@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.reply_to(message, "Nie znam tej komendy. Użyj /stworz, /tak, /nie.")

# ---------------------------------------
# START BOTA
# ---------------------------------------
if __name__ == "__main__":
    logging.info("Bot wystartował.")
    bot.infinity_polling()
