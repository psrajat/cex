import tomli
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DBConfig:
    host: str
    name: str
    user: str
    password: str


def load_config(config_path: str = "config.toml") -> DBConfig:
    path = Path(config_path)
    if not path.exists():
        # Default fallback if file is missing
        return DBConfig(host="localhost", name="cex", user="postgres", password="")

    with open(path, "rb") as f:
        data = tomli.load(f)
        db_data = data.get("database", {})
        return DBConfig(
            host=db_data.get("host", "localhost"),
            name=db_data.get("name", "cex"),
            user=db_data.get("user", "postgres"),
            password=db_data.get("password", ""),
        )
