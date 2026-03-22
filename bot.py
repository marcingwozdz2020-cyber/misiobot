import os
import time
import telebot
import feedparser
import schedule
from openai import OpenAI

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=polityka+Polska&hl=pl&gl=PL&ceid=PL:pl",
    "https://wiadomosci.onet.pl/kraj/rss.xml",
    "https://wydarzenia.interia.pl/polska/feed",
]

def fetch_news():
    items = []
    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if title:
                items.append(f"- {title} ({link})")

    unique = []
    seen = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)

    return unique[:10]

def generate_post(news_items):
    prompt = "\n".join(news_items)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """Jesteś Misiobotem.

Na podstawie listy newsów wybierz 1 temat, który najlepiej nadaje się na polityczny wpis na X.
Następnie przygotuj:

1. krótki opis wybranego tematu
2. 3 wersje wpisu:
- inteligentna riposta
- zjadliwy atak
- hashtagowy pocisk

Zasady:
- po polsku
- krótko
- naturalnie
- bez wulgaryzmów
- z pazurem
- można dodać 1-2 emoji
- każda wersja ma kończyć się: #celPolska

Format:
TEMAT: ...
1. ...
2. ...
3. ...
"""
            },
            {"role": "user", "content": f"Oto newsy:\n{prompt}"}
        ]
    )

    return response.choices[0].message.content.strip()

def send_auto_post():
    try:
        news_items = fetch_news()

        if not news_items:
            bot.send_message(TELEGRAM_CHAT_ID, "Brak newsów do analizy.")
            return

        result = generate_post(news_items)
        bot.send_message(TELEGRAM_CHAT_ID, f"🇵🇱 Misiobot Auto\n\n{result}")
    except Exception as e:
        bot.send_message(TELEGRAM_CHAT_ID, f"❌ Błąd Misiobota Auto:\n{e}")

@bot.message_handler(commands=["start"])
def start(msg):
    bot.reply_to(
        msg,
        "🇵🇱 Misiobot Auto działa\n\n/testauto - ręczny test automatu\n/temat [tekst] - ręczne generowanie"
    )

@bot.message_handler(commands=["testauto"])
def testauto(msg):
    bot.reply_to(msg, "Uruchamiam automat...")
    send_auto_post()

@bot.message_handler(commands=["temat"])
def temat(msg):
    parts = msg.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(msg, "Podaj temat po komendzie, np. /temat Tusk i deficyt")
        return

    topic = parts[1].strip()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """Przygotuj 3 krótkie wersje wpisu na X po polsku:
1. inteligentna riposta
2. zjadliwy atak
3. hashtagowy pocisk

Każda wersja ma kończyć się: #celPolska
"""
            },
            {"role": "user", "content": topic}
        ]
    )

    bot.send_message(msg.chat.id, response.choices[0].message.content.strip())

def run_scheduler():
    schedule.every().day.at("08:00").do(send_auto_post)
    schedule.every().day.at("13:00").do(send_auto_post)
    schedule.every().day.at("20:00").do(send_auto_post)

    while True:
        schedule.run_pending()
        time.sleep(20)

if __name__ == "__main__":
    import threading
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    bot.infinity_polling(timeout=60, long_polling_timeout=60)