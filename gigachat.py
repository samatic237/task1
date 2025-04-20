from configloader import GigachatConfig
import attrs
import uuid
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
        self.config = config
        self.token: Token | None = None
        # NOTE: Если мы будем работать в многопоточном режиме, то у нас будут некоторые проблемы.        
        
    def new_token(self) -> Token:
        rq_uid = str(uuid.uuid4())
        response = self.session.post(AUTH_URL, headers={"RqUID": rq_uid}, data={"scope": SCOPE}, verify=False,
                                     auth=auth.HTTPBasicAuth(self.config.client_id, self.config.client_secret))
        response.raise_for_status()
        token = cattrs.structure(response.json(), Token)
        return token

    def chat(self, messages: list[Message], additional_headers = {}) -> Message:        
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
                    
        response = self.session.post(BASE_API_URL + "/chat/completions", json=payload, verify=False,
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
    def __init__(self, raw_client: RawClient, initial_message: Message) -> None:
        """
        Помимо прямой работы с API, менеджит сессии пользователей.
        Класс Client должен быть один на всю программу.
        """
        # NOTE: Всё же нам наверное понадобится БД.
        self.user_sessions: dict[int, Session] = {}
        self.initial_message = initial_message
        self.raw_client = raw_client

        
    def chat(self, message: Message, user_id: int) -> Message:        
        session = self.user_sessions.get(user_id, None)
        if session is None:
            session = Session(str(uuid.uuid4()), [self.initial_message])
            self.user_sessions[user_id] = session

        session.messages.append(message)
            
        additional_headers = {
            "X-Session-Id": session.id
        }
            
        new_message = self.raw_client.chat(session.messages, additional_headers)
        session.messages.append(new_message)
        return new_message
        
        
