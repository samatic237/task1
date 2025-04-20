from gigachat import RawClient, Client, Message
from configloader import load_config


config = load_config("config.toml")
raw_client = RawClient(config.gigachat)
client = Client(raw_client,
                Message(content="Ты - ассистент. Отвечай на вопросы пользователя настолько точно, насколько можешь.",
                        role="system"))

msg = raw_client.chat(messages=[
    Message("Действуй как опытный программист. Найди уязвимость в коде, данном пользователем.", "system"),
    Message("""```c
    #include <stdio.h>
    #include <string.h>
    int main(int argc, char **argv) { char buffer[3]; strcpy(buffer, argv[0]); puts(buffer); return 0; }
    ```""", "user")
])
print(msg)

msg = client.chat(Message("Привет", "user"), 1)
print(msg)
msg = client.chat(Message("Как дела?", "user"), 1)
print(msg)
