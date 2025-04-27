import tomllib
import attrs
import cattrs
from pathlib import Path


@attrs.define(frozen=True)
class TelegramConfig:
    api_key: str

    
@attrs.define(frozen=True)
class GigachatConfig:
    client_id: str
    client_secret: str

    
@attrs.define(frozen=True)
class DatabaseConfig:
    path: Path

    
@attrs.define(frozen=True)
class Config:
    telegram: TelegramConfig
    gigachat: GigachatConfig
    database: DatabaseConfig

    
def load_config(path: str) -> Config:
    with open(path, "rb") as cfg:
        cfg_raw = tomllib.load(cfg)        
    cfg = cattrs.structure(cfg_raw, Config)
    parent = cfg.database.path.parent
    if not parent.exists():
        parent.mkdir(parents=True)
    return cfg


