import os
import telebot
from textwrap import shorten

# --- KONFIGURACJA ---

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Pamięć na propozycje „tweetów" per użytkownik
pending_tweets = {}


# --- GENERATOR POLITYCZNYCH „TWEETÓW" ---

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
        "Spotkanie przywódców w sprawie energii i obronności",
    ]

def generate_political_tweet(topic: str) -> str:
    """
    Generuje krótki, „tweetopodobny" tekst o polityce.
    """
    headlines = fetch_political_news()
    body = "; ".join(headlines[:3])

    tweet = f"Polityka ({topic}): {body}"
    tweet = shorten(tweet, width=260, placeholder="...")

    return tweet


# --- KOMENDY TELEGRAM ---


@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        "Cześć! Jestem botem politycznym.\n"
        "Użyj:\n"
        "/stworz [temat] – wygeneruję propozycję tweeta\n"
        "/tak – zaakceptujesz ostatnią propozycję\n"
        "/nie – odrzucisz ostatnią propozycję\n\n"
        "Nie publikuję niczego na X – tylko generuję teksty do akceptacji."
    )


@bot.message_handler(commands=['stworz'])
def stworz(message):
    # temat po /stworz
    topic = message.text.replace('/stworz', '', 1).strip()
    if not topic:
        topic = "polityka mieszana"

    generated = generate_political_tweet(topic)
    pending_tweets[message.chat.id] = generated

    bot.reply_to(
        message,
        f"Propozycja tweeta:\n\n{generated}\n\nAkceptujesz? /tak /nie"
    )


@bot.message_handler(commands=['tak'])
def accept(message):
    tweet = pending_tweets.get(message.chat.id)
    if not tweet:
        bot.reply_to(message, "Nie mam żadnej propozycji do akceptacji.")
        return

    bot.reply_to(
        message,
        f"Zatwierdzono ✅\n\nOto zaakceptowany tekst:\n\n{tweet}"
    )
    pending_tweets.pop(message.chat.id, None)


@bot.message_handler(commands=['nie'])
def reject(message):
    if message.chat.id in pending_tweets:
        pending_tweets.pop(message.chat.id, None)
        bot.reply_to(message, "OK, odrzuciłem. Użyj /stworz, aby wygenerować nową propozycję.")
    else:
        bot.reply_to(message, "Nie mam żadnej propozycji do odrzucenia.")


@bot.message_handler(func=lambda m: True)
def fallback(message):
    bot.reply_to(message, "Nie znam tej komendy. Użyj /stworz, /tak, /nie lub /start.")


if __name__ == "__main__":
    bot.infinity_polling()