from configloader import GigachatConfig, DatabaseConfig
import sqlite3
import attrs
import uuid
import threading
import requests
from requests import auth
import cattrs
import time

MODEL = "GigaChat"

AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
BASE_API_URL = "https://gigachat.devices.sberbank.ru/api/v1"


# NOTE: Временно захардкодил. В идеале, нужно будет сделать это частью конфигурации.
SCOPE = "GIGACHAT_API_PERS"


@attrs.define(frozen=True) 
class Token:
    access_token: str
    expires_at: int

    
@attrs.define(frozen=True)
class Message:
    content: str
    role: str

    
@attrs.define
class Session:
    id: str
    messages: list[Message]


class RawClient:    
    def __init__(self, config: GigachatConfig) -> None:
        """Класс RawClient должен быть один на всю программу."""
        self.session = requests.Session()
        self.session.verify = False
        self.config = config
        self.token: Token | None = None
        self.token_lock = threading.Lock()
        
    def new_token(self) -> Token:
        rq_uid = str(uuid.uuid4())
        response = self.session.post(AUTH_URL, headers={"RqUID": rq_uid}, data={"scope": SCOPE},
                                     auth=auth.HTTPBasicAuth(self.config.client_id, self.config.client_secret))
        response.raise_for_status()
        token = cattrs.structure(response.json(), Token)
        return token

    def chat(self, messages: list[Message], additional_headers = {}) -> Message:
        # Надеюсь, этого достаточно.
        with self.token_lock:
            if self.token is None or round(time.time() * 1000) >= self.token.expires_at:
                self.token = self.new_token()
        payload = {
            "model": MODEL,
            "messages": cattrs.unstructure(messages),
        }
        headers = {
            "Authorization": f"Bearer {self.token.access_token}",
        }
        headers.update(additional_headers)
                    
        response = self.session.post(BASE_API_URL + "/chat/completions", json=payload,
                                     headers=headers)
        
        
        data = response.json()
        response.raise_for_status()        
        for raw_msg in data["choices"]:
            if raw_msg["finish_reason"] == "error":
                continue
            new_message = cattrs.structure(raw_msg["message"], Message)
            return new_message
        raise Exception("Нет ответа без ошибки >:")


class Client:    
    def __init__(self, config: DatabaseConfig, raw_client: RawClient, initial_message: Message) -> None:
        """
        Помимо прямой работы с API, менеджит сессии пользователей.
        Класс Client должен быть один на всю программу.
        """
        self.connection = sqlite3.connect(config.path, check_same_thread=False)
        self.connection_lock = threading.Lock()
        self.initial_message = initial_message
        self.raw_client = raw_client
        self.initialize_database()
        
    def initialize_database(self):
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (user_id INTEGER PRIMARY KEY NOT NULL, session_uuid TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (message_id INTEGER PRIMARY KEY NOT NULL, user_id INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL);
        """) 

    def get_or_create_session(self, user_id: int) -> Session:
        session_uuid: str
        with self.connection_lock:
            with self.connection:
                cur = self.connection.cursor()
                result = cur.execute("SELECT session_uuid FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
                if result is None:
                    session_uuid = str(uuid.uuid4())
                    cur.execute("INSERT INTO sessions (user_id, session_uuid) VALUES (?, ?)", (user_id, session_uuid))
                    cur.execute("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)", (user_id, self.initial_message.role, self.initial_message.content))
                    cur.close()                    
                    return Session(session_uuid, [self.initial_message])
                session_uuid = result[0]
                session = Session(session_uuid, list(map(lambda tup: Message(tup[1], tup[0]),
                                                         cur.execute("SELECT role, content FROM messages WHERE user_id = ? ORDER BY message_id",
                                                                     (user_id,)))))
                cur.close()
                return session

    def add_messages(self, messages: list[Message], user_id: int) -> None:
        with self.connection_lock:
            with self.connection:
                self.connection.executemany("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                                            map(lambda m: (user_id, m.role, m.content), messages))
        
    def chat(self, message: Message, user_id: int) -> Message:
        session = self.get_or_create_session(user_id)
            
        additional_headers = {
            "X-Session-Id": session.id
        }

        session.messages.append(message)
        new_message = self.raw_client.chat(session.messages, additional_headers)        
        self.add_messages([message, new_message], user_id)
        
        return new_message
        
        
