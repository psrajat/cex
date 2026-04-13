import tomli
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DBConfig:
    """Connection parameters for the PostgreSQL database."""
    host:     str
    name:     str
    user:     str
    password: str


@dataclass
class LLMConfig:
    """Settings for the chat/completion LLM (OpenAI-compatible server).

    All fields map 1-to-1 to the ``[llm]`` section in config.toml.
    ``base_url`` must point to an OpenAI-compatible ``/v1`` endpoint
    (Ollama, LocalAI, llama.cpp server, etc.).
    """
    base_url:    str   = "http://localhost:11434/v1"
    model:       str   = "qwen2.5-coder:7b"
    api_key:     str   = "ollama"
    max_tokens:  int   = 2048
    temperature: float = 0.1


@dataclass
class EmbedConfig:
    """Settings for the text-embedding model used by ``cex embed``.

    Kept separate from LLMConfig because embedding and chat models are
    often different binaries / endpoints, and batch_size is embeddings-specific.

    ``dim`` must match the output dimension of ``model`` exactly — it is used
    to create the ``VECTOR(dim)`` column in the database during ``cex setup``.
    Changing it after the first ``cex setup`` requires a ``cex reset``.
    """
    model:      str = "nomic-embed-text"
    dim:        int = 768
    batch_size: int = 32


@dataclass
class AppConfig:
    """Top-level config container.  Callers receive this from load_config()."""
    db:    DBConfig
    llm:   LLMConfig   = field(default_factory=LLMConfig)
    embed: EmbedConfig = field(default_factory=EmbedConfig)


def load_config(config_path: str = "config.toml") -> AppConfig:
    """Load configuration from a TOML file and return an AppConfig.

    Falls back to default values for any missing sections or keys.
    Missing file → returns an AppConfig with all defaults.
    """
    path = Path(config_path)
    if not path.exists():
        return AppConfig(db=DBConfig(host="localhost", name="cex", user="postgres", password=""))

    with open(path, "rb") as f:
        data = tomli.load(f)

    db_data = data.get("database", {})
    db = DBConfig(
        host=db_data.get("host", "localhost"),
        name=db_data.get("name", "cex"),
        user=db_data.get("user", "postgres"),
        password=db_data.get("password", ""),
    )

    llm_data = data.get("llm", {})
    llm = LLMConfig(
        base_url=llm_data.get("base_url",    LLMConfig.base_url),
        model=llm_data.get("model",          LLMConfig.model),
        api_key=llm_data.get("api_key",      LLMConfig.api_key),
        max_tokens=llm_data.get("max_tokens", LLMConfig.max_tokens),
        temperature=llm_data.get("temperature", LLMConfig.temperature),
    )

    embed_data = data.get("embed", {})
    embed = EmbedConfig(
        model=embed_data.get("model",           EmbedConfig.model),
        dim=embed_data.get("dim",               EmbedConfig.dim),
        batch_size=embed_data.get("batch_size", EmbedConfig.batch_size),
    )

    return AppConfig(db=db, llm=llm, embed=embed)
