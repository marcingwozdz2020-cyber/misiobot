import telebot
import os
from openai import OpenAI

bot = telebot.TeleBot(os.environ["TELEGRAM_TOKEN"])
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def generate(topic):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Generuj 3 krótkie polityczne wpisy po polsku: riposta, atak, pocisk. Zakończ #celPolska"},
            {"role": "user", "content": topic}
        ]
    )
    return response.choices[0].message.content

@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "🇵🇱 Misiobot działa\n\n/temat [tekst]")

@bot.message_handler(commands=['temat'])
def temat(msg):
    text = msg.text.replace("/temat", "").strip()
    if not text:
        bot.reply_to(msg, "Podaj temat")
        return
    bot.reply_to(msg, "Myślę...")
    result = generate(text)
    bot.send_message(msg.chat.id, result)

bot.infinity_polling()
