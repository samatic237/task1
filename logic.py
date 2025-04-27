import telebot
from configloader import load_config
import gigachat

PROMPT = gigachat.Message("Ты - добрый ассистент.", "system")

cfg = load_config("config.toml")

bot = telebot.TeleBot(cfg.telegram.api_key)
client = gigachat.Client(cfg.database,
                         gigachat.RawClient(cfg.gigachat), PROMPT)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, 'Привет! Напиши что-нибудь!')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user_request = message.text

    response = client.chat(gigachat.Message(content=user_request,
                                            role="user"), user_id)

    bot.send_message(message.chat.id, response.content)

# Запуск бота
if __name__ == "__main__":
    bot.polling(none_stop=True)
