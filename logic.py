import telebot
from configloader import load_config
import gigachat

PROMPT = gigachat.Message("Ты - менеджер по карьере.", "system")

cfg = load_config("config.toml")

bot = telebot.TeleBot(cfg.telegram.api_key)
database = gigachat.Database(cfg.database)
client = gigachat.Client(gigachat.RawClient(cfg.gigachat), database, PROMPT)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, 'Привет! Напиши что-нибудь!')

@bot.message_handler(commands=['prompt'])
def handle_command(message):
    args = message.text.split(' ', 1)
    if len(args) > 1:
        user_input = args[1]
        with database.begin() as trans:
            trans.reset_session(message.from_user.id,
                                gigachat.Message(content=user_input, role="system"))
        bot.reply_to(message, f"Вы ввели: {user_input}")
    else:
        bot.reply_to(message, "Пожалуйста, укажите аргумент после команды")
        
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
