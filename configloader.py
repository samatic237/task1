import tomllib
import attrs
import cattrs


@attrs.define(frozen=True)
class TelegramConfig:
    api_key: str

    
@attrs.define(frozen=True)
class GigachatConfig:
    client_id: str
    client_secret: str


@attrs.define(frozen=True)
class Config:
    telegram: TelegramConfig
    gigachat: GigachatConfig

    
def load_config(path: str) -> Config:
    with open(path, "rb") as cfg:
        cfg_raw = tomllib.load(cfg)
        return cattrs.structure(cfg_raw, Config)


