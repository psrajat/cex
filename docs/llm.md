# cex — LLM Client

Wraps any OpenAI-compatible local LLM server (Ollama, LocalAI, llama.cpp).

---

## Entry Points

```
cex embed    →  LLMClient.embed()
cex explain  →  LLMClient.chat()
```

---

## LLMClient

`llm/client.py`

Synchronous `httpx.Client` — no async.  CLI tools call LLMs sequentially; async adds complexity with no throughput benefit here.

### `chat(messages, stream=True) -> str`

Sends a list of `{"role": ..., "content": ...}` messages to `/chat/completions`.

- **`stream=True`** (default for interactive use): tokens are printed to stdout as they arrive via SSE, and the full response string is returned.
- **`stream=False`** (used by `explain --all`): response is returned silently, no printing.

**SSE parsing**: each `data: {...}` line is decoded; `choices[0].delta.content` is accumulated.  Lines that fail to parse are skipped without crashing.

### `embed(texts) -> list[list[float]]`

Sends a batch of texts to `/embeddings`.  Returns one vector per input, sorted by `index` to guarantee order matches input.

The model used is `LLMConfig.embed_model` (separate from the chat model).

---

## Prompts (`llm/prompts.py`)

Pure functions — no I/O, no DB access.  Each builder returns a `messages` list.

### `build_explain_prompt(symbol, parent, callers, callees) -> list[dict]`

Constructs the explain prompt with four sections:

```
SYMBOL: <qualified_name>  TYPE: <type>  FILE: <path>

--- CODE ---
<full code_body>

--- PARENT ---          (if symbol is a method)
<parent.signature>

--- CALLED BY ---        (up to 5, signatures only)
<caller.qualified_name>: <caller.signature>

--- CALLS ---            (up to 5, signatures only)
<callee.qualified_name>: <callee.signature>
```

**Context budget design**: neighbours are included as signatures only (one line each).  The current symbol's `code_body` already shows *how* they are called — full bodies would waste context tokens on a local LLM with limited context windows.

### System prompt

The system prompt instructs the LLM to respond with exactly four labelled sections:
- `SUMMARY:` — one sentence
- `PURPOSE:` — problem it solves
- `HOW IT WORKS:` — 3–5 numbered steps
- `NOTABLE:` — edge cases, exceptions, side effects

No JSON, no markdown fences.  Plain text is easier to stream, cache, and read.

---

## Configuration

All settings in `config.toml [llm]`:

| Key | Purpose |
|---|---|
| `base_url` | API server root (e.g. `http://localhost:11434/v1`) |
| `model` | Chat model name |
| `embed_model` | Embedding model name (can differ from chat model) |
| `embed_dim` | Vector dimension — must match the embed model |
| `api_key` | Sent as `Authorization: Bearer <key>` (ignored by most local servers) |
| `max_tokens` | Max response length |
| `temperature` | 0.1 recommended for code explanation (near-deterministic) |

---

## Adding a New Prompt

Add a new builder to `llm/prompts.py`:

```python
def build_my_prompt(symbol: SymbolModel, ...) -> list[dict]:
    return [
        {"role": "system", "content": "..."},
        {"role": "user",   "content": "..."},
    ]
```

Then call `client.chat(build_my_prompt(...))` in the relevant engine.  No other files need changing.
