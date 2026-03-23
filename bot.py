import os
import logging
import sqlite3
import feedparser
import telebot
from datetime import datetime
from openai import OpenAI
from textwrap import shorten

# --- Konfiguracja ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Pobieranie tokenów z env
TELEGRAM_TOKEN = os.environ.get("telegram_token")
OPENAI_API_KEY = os.environ.get("openai_api_key")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Brakuje zmiennych środowiskowych: telegram_token lub openai_api_key")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Baza danych ---
conn = sqlite3.connect("tweets.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS tweets (id INTEGER PRIMARY KEY AUTOINCREMENT, tweet TEXT, created_at TIMESTAMP)")
conn.commit()

pending_tweets = {}

# --- Logika Pobierania i Generowania ---

def get_latest_news():
    """POPRAWIONE: Pobiera prawdziwy kanał RSS z Google News PL."""
    url = "https://news.google.com"
    feed = feedparser.parse(url)
    # Pobieramy 5 najnowszych tytułów
    titles = [entry.title for entry in feed.entries[:5]]
    return "\n".join(titles) if titles else "Brak bieżących nagłówków w RSS."

def generate_ai_tweet(topic: str) -> str:
    """POPRAWIONE: Dostęp do atrybutów odpowiedzi OpenAI (v1.0+)."""
    news_context = get_latest_news()
    
    prompt = f"""
    Jesteś ekspertem od marketingu politycznego. Na podstawie poniższych newsów:
    {news_context}
    
    Napisz krótki, angażujący tweet na temat: {topic}. 
    Tweet musi być w języku polskim, zawierać max 240 znaków i pasować do stylu Twittera.
    Nie używaj hashtagów.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150
        )
        # POPRAWKA: Prawidłowa ścieżka do treści w nowej bibliotece OpenAI
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Błąd OpenAI: {e}")
        return f"Błąd podczas generowania przez AI: {str(e)}"

# --- Handlery ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "🤖 Bot aktywny! Wpisz /generate [temat], aby stworzyć tweet na bazie newsów.")

@bot.message_handler(commands=['generate'])
def handle_generate(message):
    args = message.text.split(maxsplit=1)
    topic = args[1] if len(args) > 1 else "aktualna sytuacja polityczna"
    
    bot.send_chat_action(message.chat.id, 'typing')
    tweet = generate_ai_tweet(topic)
    
    pending_tweets[message.chat.id] = tweet
    bot.reply_to(message, f"🤖 **AI wygenerowało:**\n\n{tweet}\n\nUżyj /save aby zapisać do bazy.")

@bot.message_handler(commands=['save'])
def handle_save(message):
    tweet = pending_tweets.get(message.chat.id)
    if tweet:
        cursor.execute("INSERT INTO tweets (tweet, created_at) VALUES (?, ?)", (tweet, datetime.now()))
        conn.commit()
        bot.reply_to(message, "✅ Zapisano w bazie!")
        del pending_tweets[message.chat.id]
    else:
        bot.reply_to(message, "Brak tweeta do zapisu. Najpierw /generate.")

if __name__ == "__main__":
    logging.info("Bot AI wystartował...")
    bot.infinity_polling()
