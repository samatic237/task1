import telebot
from gigachat import Client
API_TOKEN = 'YOUR_TOKEN_HERE'

bot = telebot.TeleBot(API_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, 'Привет! Напиши что-нибудь!')

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user_request = message.text

    response = Client.chat(user_request,user_id)

    bot.send_message(message.chat.id, response)

# Запуск бота
if __name__ == "__main__":
    bot.polling(none_stop=True)