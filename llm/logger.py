"""llm/logger.py

Appends a human-readable record of every prompt sent to the LLM to a log file.

Enabled only when ``[logging] log_prompts = true`` in config.toml.
The log is plain text so it can be tailed in a terminal during bulk runs:

    tail -f logs/prompts.log

Log format per entry:
    ══... header with timestamp and symbol name
    [SYSTEM]  — the system instruction sent to the model
    [USER]    — the code context assembled by build_explain_prompt()
    ──... footer separator

Each entry is appended atomically (open in append mode), so concurrent
processes writing to the same file won't interleave mid-entry in practice
(the OS write syscall for small strings is atomic on most filesystems).
"""

from datetime import datetime
from pathlib import Path

from config import LoggingConfig


def log_prompt(messages: list[dict], symbol_id: str, cfg: LoggingConfig) -> None:
    """Append one prompt record to the log file.

    ``messages`` — the list of ``{"role": ..., "content": ...}`` dicts as
                   returned by ``build_explain_prompt()``.
    ``symbol_id`` — the qualified name of the symbol being explained.
    ``cfg``        — LoggingConfig; if ``log_prompts`` is False this is a no-op.
    """
    if not cfg.log_prompts:
        return

    log_path = Path(cfg.log_dir) / "prompts.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    divider_heavy = "═" * 72
    divider_light = "─" * 72

    parts = [
        f"\n{divider_heavy}",
        f"PROMPT LOG  {timestamp}",
        f"SYMBOL      {symbol_id}",
        divider_heavy,
    ]

    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        parts.append(f"\n[{role}]")
        parts.append(content)

    parts.append(f"\n{divider_light}\n")

    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
