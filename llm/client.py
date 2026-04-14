"""llm/client.py

Synchronous LLM client for any OpenAI-compatible server (Ollama, LocalAI, llama.cpp).

Two capabilities:
  chat()  — send a message list, optionally stream tokens to stdout.
  embed() — encode a batch of texts into embedding vectors.

Chat and embedding can use different models (via separate config sections) but
share the same HTTP connection to the same base_url / api_key endpoint.
"""

import json
from collections.abc import Generator

import httpx

from config import EmbedConfig, LLMConfig


class LLMClient:
    """HTTP client for OpenAI-compatible chat and embedding endpoints.

    A single ``httpx.Client`` is used for both chat and embed requests because
    Ollama (and most compatible servers) route both on the same base URL.  The
    model names differ: LLMConfig.model for chat, EmbedConfig.model for embed.
    """

    def __init__(self, llm: LLMConfig, embed: EmbedConfig):
        self._llm = llm
        self._embed = embed
        self._http = httpx.Client(
            base_url=llm.base_url,
            headers={"Authorization": f"Bearer {llm.api_key}"},
            timeout=600.0,  # local LLMs can be slow on first token
            transport=httpx.HTTPTransport(retries=3),
        )

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._http.close()

    # ── Chat ─────────────────────────────────────────────────────────────────

    def chat(self, messages: list[dict], stream: bool = True) -> str:
        """Send a chat completion request.

        When stream=True, tokens are printed to stdout as they arrive and the
        full response string is returned.  When stream=False, the response is
        returned silently (used by explain_all bulk mode).
        """
        payload = {
            "model": self._llm.model,
            "messages": messages,
            "stream": stream,
            "max_tokens": self._llm.max_tokens,
            "temperature": self._llm.temperature,
        }

        if stream:
            return self._stream_chat(payload)

        resp = self._http.post("/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _stream_chat(self, payload: dict) -> str:
        """Consume an SSE stream, printing each token and collecting the full text."""
        parts: list[str] = []
        with self._http.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        print(delta, end="", flush=True)
                        parts.append(delta)
                except (json.JSONDecodeError, KeyError, IndexError):
                    # Malformed SSE chunk — skip silently rather than crashing.
                    continue
        print()  # trailing newline after stream ends
        return "".join(parts)

    def stream_chat(self, messages: list[dict]) -> Generator[str, None, None]:
        """Yield raw token strings from a streaming completion without printing.

        Unlike chat(stream=True) which echoes tokens to stdout for CLI use,
        this generator is intended for callers that consume the tokens
        programmatically (e.g. the FastAPI SSE endpoint).
        """
        payload = {
            "model": self._llm.model,
            "messages": messages,
            "stream": True,
            "max_tokens": self._llm.max_tokens,
            "temperature": self._llm.temperature,
        }
        with self._http.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    # ── Embeddings ────────────────────────────────────────────────────────────

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Encode a list of texts and return one embedding vector per input.

        Texts are sent as a single batch.  The response items are sorted by
        their ``index`` field to guarantee the output order matches the input.
        """
        if not texts:
            return []

        payload = {"model": self._embed.model, "input": texts}
        resp = self._http.post("/embeddings", json=payload)
        resp.raise_for_status()

        data = resp.json()["data"]
        # Sort by index to guarantee order matches input regardless of server behaviour.
        data.sort(key=lambda x: x["index"])
        return [item["embedding"] for item in data]

