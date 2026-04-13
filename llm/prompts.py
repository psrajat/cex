"""llm/prompts.py

Pure prompt builders — no I/O, no DB access, no side effects.

Each function returns a ``messages`` list ready to pass to LLMClient.chat().
Context is carefully budgeted: full code bodies for the target symbol,
signatures only for 1-hop neighbours, to stay within local model context limits.
"""

from ingestion.models import SymbolModel

# ── System prompts ────────────────────────────────────────────────────────────

_EXPLAIN_SYSTEM = """\
You are a concise, precise code explainer. Reply with exactly these four sections \
and no other text:

SUMMARY: one sentence describing what this symbol is
PURPOSE: the problem it solves or role it plays in the system
HOW IT WORKS: 3-5 numbered steps walking through the logic
NOTABLE: edge cases, exceptions raised, state mutations, or important side effects\
"""


# ── Builders ──────────────────────────────────────────────────────────────────

def build_explain_prompt(
    symbol: SymbolModel,
    parent: SymbolModel | None,
    callers: list[SymbolModel],
    callees: list[SymbolModel],
) -> list[dict]:
    """Build the explain prompt for a single symbol.

    Neighbourhood context (callers/callees) is included as signatures only —
    the current symbol's code_body already shows how they are used, so full
    bodies would waste context tokens.
    """
    lines: list[str] = [
        f"SYMBOL: {symbol.qualified_name}  TYPE: {symbol.type}  FILE: {symbol.file_path}",
        "",
        "--- CODE ---",
        symbol.code_body,
    ]

    if parent:
        lines += ["", "--- PARENT ---", parent.signature]

    if callers:
        lines += ["", "--- CALLED BY ---"]
        for c in callers[:5]:
            lines.append(f"{c.qualified_name}: {c.signature}")

    if callees:
        lines += ["", "--- CALLS ---"]
        for c in callees[:5]:
            lines.append(f"{c.qualified_name}: {c.signature}")

    return [
        {"role": "system", "content": _EXPLAIN_SYSTEM},
        {"role": "user",   "content": "\n".join(lines)},
    ]
