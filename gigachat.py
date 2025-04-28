from configloader import GigachatConfig, DatabaseConfig
import sqlite3
import attrs
import uuid
import threading
import requests
from requests import auth
from collections.abc import Iterator
import cattrs
import time
from contextlib import contextmanager

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


LIMIT = 10

class RawClient:    
    def __init__(self, config: GigachatConfig) -> None:
        """Класс RawClient должен быть один на всю программу."""
        self.session = requests.Session()
        self.config = config
        self.token: Token | None = None
        self.token_lock = threading.Lock()
        self.conn_semaphore = threading.BoundedSemaphore(LIMIT)
        
    def new_token(self) -> Token:
        rq_uid = str(uuid.uuid4())
        response = self.session.post(AUTH_URL, headers={"RqUID": rq_uid}, data={"scope": SCOPE}, verify=False,
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

        with self.conn_semaphore:
            response = self.session.post(BASE_API_URL + "/chat/completions", json=payload,
                                         headers=headers, verify=False)
            
        response.raise_for_status()                
        data = response.json()

        for raw_msg in data["choices"]:
            if raw_msg["finish_reason"] == "error":
                continue
            new_message = cattrs.structure(raw_msg["message"], Message)
            return new_message
        raise Exception("Нет ответа без ошибки >:")


class Trans:
    def __init__(self, cur: sqlite3.Cursor) -> None:
        self.cur = cur
        
    def get_session(self, user_id: int) -> Session | None:
        result = self.cur.execute("SELECT session_uuid FROM sessions WHERE user_id = ?", (user_id,)).fetchone()
        if result is None:
            return None
        session_uuid = result[0]
        messages = [Message(content=m[0], role=m[1])
                    for m in self.cur.execute("SELECT content, role FROM messages WHERE user_id = ? ORDER BY message_id", (user_id,))]
        return Session(session_uuid, messages)

    def delete_session(self, user_id: int) -> None:
        self.cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        self.cur.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    
    def create_session(self, user_id: int, initial_message: Message) -> Session:
        session_uuid = str(uuid.uuid4())
        self.cur.execute("INSERT INTO sessions (user_id, session_uuid) VALUES (?, ?)", (user_id, session_uuid))
        self.cur.execute("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)", (user_id, initial_message.role, initial_message.content))
        return Session(session_uuid, [initial_message])

    def reset_session(self, user_id: int, initial_message: Message) -> None:
        self.delete_session(user_id)
        self.create_session(user_id, initial_message)
    
    def get_or_create_session(self, user_id: int, initial_message: Message) -> Session:
        return self.get_session(user_id) or self.create_session(user_id, initial_message)

    def add_messages(self, messages: list[Message], user_id: int) -> None:
        self.cur.executemany("INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
                             ((user_id, message.role, message.content) for message in messages))            

class Database:
    def __init__(self, config: DatabaseConfig) -> None:
        self.connection = sqlite3.connect(config.path, check_same_thread=False)
        self.connection_lock = threading.Lock()
        self.init()
        
    # NOTE: Не thread-safe
    def init(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (user_id INTEGER PRIMARY KEY NOT NULL, session_uuid TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (message_id INTEGER PRIMARY KEY NOT NULL, user_id INTEGER NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL);
        """)

    @contextmanager
    def begin(self) -> Iterator[Trans]:
        with self.connection_lock:
            with self.connection:
                cur = self.connection.cursor()
                yield Trans(cur)
                cur.close()
    
class Client:    
    def __init__(self, raw_client: RawClient, database: Database, initial_message: Message) -> None:
        """
        Помимо прямой работы с API, менеджит сессии пользователей.
        Класс Client должен быть один на всю программу.
        """

        self.initial_message = initial_message
        self.raw_client = raw_client
        self.database = database
        
    def chat(self, message: Message, user_id: int) -> Message:
        with self.database.begin() as trans:
            session = trans.get_or_create_session(user_id, self.initial_message)

        additional_headers = {
            "X-Session-Id": session.id
        }

        session.messages.append(message)
        new_message = self.raw_client.chat(session.messages, additional_headers)
        
        with self.database.begin() as trans:
            trans.add_messages([message, new_message], user_id)
        
        return new_message
        
        
