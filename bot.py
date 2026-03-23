import os
import time
import logging
import telebot
import feedparser
import schedule
from openai import OpenAI
from functools import wraps
from typing import List, Optional

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Walidacja zmiennych środowiskowych
def validate_env_vars():
    """Sprawdza czy wszystkie wymagane zmienne środowiskowe są ustawione."""
    required_vars = ["TELEGRAM_TOKEN", "OPENAI_API_KEY", "TELEGRAM_CHAT_ID"]
    missing_vars = [var for var in required_vars if var not in os.environ]
    
    if missing_vars:
        raise ValueError(f"Brakujące zmienne środowiskowe: {', '.join(missing_vars)}")
    
    logger.info("Wszystkie zmienne środowiskowe są ustawione")

# Inicjalizacja
try:
    validate_env_vars()
    TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
    
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("Bot i klient OpenAI zainicjalizowane pomyślnie")
except (ValueError, Exception) as e:
    logger.critical(f"Błąd inicjalizacji: {e}")
    raise

RSS_FEEDS = [
    "https://news.google.com/rss/search?q=polityka+Polska&hl=pl&gl=PL&ceid=PL:pl",
    "https://wiadomosci.onet.pl/kraj/rss.xml",
    "https://wydarzenia.interia.pl/polska/feed",
]

# Dekorator do ponawiania funkcji
def retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Dekorator do ponawiania funkcji z opóźnieniem wykładniczym."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            current_delay = delay
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.error(f"Funkcja {func.__name__} nie powiodła się po {max_attempts} próbach: {e}")
                        raise
                    
                    logger.warning(f"Próba {attempt}/{max_attempts} dla {func.__name__} nie powiodła się. Retry za {current_delay}s: {e}")
                    time.sleep(current_delay)
                    current_delay *= backoff
        
        return wrapper
    return decorator

def remove_duplicates(items: List[str]) -> List[str]:
    """
    Usuwa duplikaty z listy zachowując kolejność.
    
    Args:
        items: Lista artykułów
        
    Returns:
        Lista unikalnych artykułów
    """
    seen = set()
    unique = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique

@retry(max_attempts=3, delay=1.0)
def fetch_news() -> List[str]:
    """
    Pobiera i parsuje artykuły z predefiniowanych kanałów RSS.
    Ogranicza do 5 artykułów na kanał i usuwa duplikaty.
    
    Returns:
        List[str]: Lista sformatowanych stringów artykułów (max 10)
        
    Raises:
        Exception: Jeśli parsowanie RSS się nie powiedzie
    """
    items = []
    
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            
            # Sprawdzenie czy feed został poprawnie sparsowany
            if feed.bozo:
                logger.warning(f"Ostrzeżenie podczas parsowania {url}: {feed.bozo_exception}")
            
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                
                if title and link:
                    items.append(f"- {title} ({link})")
                    
        except Exception as e:
            logger.error(f"Błąd podczas pobierania kanału {url}: {e}")
            continue
    
    if not items:
        raise ValueError("Nie udało się pobrać artykułów z żadnego kanału RSS")
    
    unique_items = remove_duplicates(items)
    logger.info(f"Pobrano {len(unique_items)} unikalnych artykułów")
    
    return unique_items[:10]

@retry(max_attempts=2, delay=1.0)
def generate_post(news_items: List[str]) -> str:
    """
    Generuje wpis na bazie listy newsów przy użyciu OpenAI.
    
    Args:
        news_items: Lista artykułów do analizy
        
    Returns:
        str: Wygenerowany wpis
        
    Raises:
        Exception: Jeśli API OpenAI zwróci błąd
    """
    prompt = "\n".join(news_items)
    
    try:
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
        
        # Walidacja odpowiedzi
        if not response.choices or len(response.choices) == 0:
            raise ValueError("OpenAI API nie zwrócił żadnych wyników")
        
        result = response.choices[0].message.content.strip()
        logger.info("Wpis wygenerowany pomyślnie")
        return result
        
    except Exception as e:
        logger.error(f"Błąd podczas generowania wpisu: {e}")
        raise

@retry(max_attempts=2, delay=1.0)
def send_auto_post() -> None:
    """
    Główna funkcja automatycznego wysyłania wpisów.
    Pobiera newsy, generuje wpis i wysyła go na Telegrama.
    """
    try:
        logger.info("Rozpoczęto automatyczne wysyłanie wpisu")
        news_items = fetch_news()
        
        if not news_items:
            error_msg = "Brak newsów do analizy."
            logger.warning(error_msg)
            bot.send_message(TELEGRAM_CHAT_ID, error_msg)
            return
        
        result = generate_post(news_items)
        bot.send_message(TELEGRAM_CHAT_ID, f"🇵🇱 Misiobot Auto\n\n{result}")
        logger.info("Wpis wysłany pomyślnie")
        
    except Exception as e:
        error_msg = f"❌ Błąd Misiobota Auto:\n{str(e)[:200]}"  # Ograniczenie długości
        logger.error(f"Automatyczne wysyłanie nie powiodło się: {e}", exc_info=True)
        try:
            bot.send_message(TELEGRAM_CHAT_ID, error_msg)
        except Exception as telegram_error:
            logger.error(f"Nie udało się wysłać wiadomości o błędzie: {telegram_error}")

@bot.message_handler(commands=["start"])
def start(msg) -> None:
    """Handler komendy /start."""
    logger.info(f"Komenda /start od użytkownika {msg.from_user.id}")
    bot.reply_to(
        msg,
        "🇵🇱 Misiobot Auto działa\n\n/testauto - ręczny test automatu\n/temat [tekst] - ręczne generowanie"
    )

@bot.message_handler(commands=["testauto"])
def testauto(msg) -> None:
    """Handler komendy /testauto."""
    logger.info(f"Komenda /testauto od użytkownika {msg.from_user.id}")
    bot.reply_to(msg, "Uruchamiam automat...")
    try:
        send_auto_post()
    except Exception as e:
        logger.error(f"Błąd podczas ręcznego testu: {e}")
        bot.send_message(msg.chat.id, f"❌ Błąd podczas testu: {str(e)[:200]}")

@bot.message_handler(commands=["temat"])
def temat(msg) -> None:
    """Handler komendy /temat - generuje wpis na podstawie podanego tematu."""
    logger.info(f"Komenda /temat od użytkownika {msg.from_user.id}")
    
    parts = msg.text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(msg, "Podaj temat po komendzie, np. /temat Tusk i deficyt")
        return
    
    topic = parts[1].strip()
    logger.info(f"Generowanie wpisu dla tematu: {topic}")
    
    try:
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
        
        if not response.choices or len(response.choices) == 0:
            raise ValueError("OpenAI API nie zwrócił wyników")
        
        result = response.choices[0].message.content.strip()
        bot.send_message(msg.chat.id, result)
        logger.info("Wpis wygenerowany i wysłany pomyślnie")
        
    except Exception as e:
        error_msg = f"❌ Błąd podczas generowania wpisu: {str(e)[:200]}"
        logger.error(f"Błąd: {e}", exc_info=True)
        bot.send_message(msg.chat.id, error_msg)

def run_scheduler() -> None:
    """
    Uruchamia scheduler z zaplanowanymi zadaniami.
    Wysyła automatyczne wpisy o godz. 08:00, 13:00 i 20:00.
    """
    schedule.every().day.at("08:00").do(send_auto_post)
    schedule.every().day.at("13:00").do(send_auto_post)
    schedule.every().day.at("20:00").do(send_auto_post)
    
    logger.info("Scheduler uruchomiony. Zaplanowane zadania:")
    logger.info("- 08:00 - Automatyczne wysyłanie")
    logger.info("- 13:00 - Automatyczne wysyłanie")
    logger.info("- 20:00 - Automatyczne wysyłanie")
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(20)
        except Exception as e:
            logger.error(f"Błąd w schedulerze: {e}", exc_info=True)
            time.sleep(60)  # Czekaj dłużej jeśli scheduler się wysypał

if __name__ == "__main__":
    import threading
    
    logger.info("Uruchamianie Misiobota...")
    
    try:
        # Uruchomienie schedulera w osobnym wątku
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("Wątek schedulera uruchomiony")
        
        # Główna pętla bota
        logger.info("Uruchamianie polling bota")
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except KeyboardInterrupt:
        logger.info("Bot zatrzymany przez użytkownika")
    except Exception as e:
        logger.critical(f"Krytyczny błąd: {e}", exc_info=True)
        raise