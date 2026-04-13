# cex — Configuration

## Entry Point

`load_config(config_path="config.toml") -> AppConfig`

Reads `config.toml` from the working directory and returns an `AppConfig` dataclass.  All fields have safe defaults so the tool works even without a config file.

---

## AppConfig

Top-level container returned by `load_config()`.

| Field | Type | Description |
|---|---|---|
| `db` | `DBConfig` | PostgreSQL connection settings |
| `llm` | `LLMConfig` | LLM server and model settings |

---

## DBConfig

| Field | Default | Description |
|---|---|---|
| `host` | `localhost` | PostgreSQL host |
| `name` | `cex` | Database name |
| `user` | `postgres` | Database user |
| `password` | `` | Database password |

---

## LLMConfig

| Field | Default | Description |
|---|---|---|
| `base_url` | `http://localhost:11434/v1` | OpenAI-compatible API base (Ollama default) |
| `model` | `qwen2.5-coder:7b` | Chat/completion model name |
| `embed_model` | `nomic-embed-text` | Embedding model name |
| `embed_dim` | `768` | Embedding vector dimension (must match the model) |
| `api_key` | `ollama` | API key (ignored for local servers, required by the spec) |
| `max_tokens` | `2048` | Max output tokens per LLM response |
| `temperature` | `0.1` | Sampling temperature (low = deterministic, good for code) |

---

## config.toml Example

```toml
[database]
host     = "localhost"
name     = "cex"
user     = "postgres"
password = "postgres"

[llm]
base_url    = "http://localhost:11434/v1"
model       = "qwen2.5-coder:7b"
embed_model = "nomic-embed-text"
embed_dim   = 768
api_key     = "ollama"
max_tokens  = 2048
temperature = 0.1
```

---

## Propagation

`main.py` calls `load_config()` once and passes the appropriate sub-config to each subsystem:

```
AppConfig.db  → setup_database(), reset_database(), DatabaseManager()
AppConfig.llm → LLMClient()
AppConfig.llm.embed_dim → EmbeddingEngine()
```

If you override DB credentials with `--db-*` flags on `cex ingest`, a new `DBConfig` is constructed from the flag values with `config.db.*` as defaults.
