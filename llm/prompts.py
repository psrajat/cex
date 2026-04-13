"""llm/prompts.py

Pure prompt builders — no I/O, no DB access, no side effects.

Each function returns a ``messages`` list ready to pass to LLMClient.chat().
Context is carefully budgeted: full code bodies for the target symbol,
signatures only for 1-hop neighbours, to stay within local model context limits.
"""

from ingestion.models import SymbolModel

# ── System prompts ────────────────────────────────────────────────────────────

_EXPLAIN_SYSTEM = """\
You are a senior engineer explaining code to a fellow developer who is smart but \
unfamiliar with this particular codebase.

Your goal is to be both technically precise and genuinely readable — not academic, \
not hand-wavy. Write as if you are the original author walking a new teammate through \
the code in a code review. Use real identifiers from the code. Avoid filler phrases \
like "this function handles" or "this method is responsible for" — state directly \
what it does and why.

Reply with exactly these four sections and no other text:

SUMMARY
One sentence. Name the symbol and its single clear responsibility. Mention where it \
fits in the system if that context matters.
Good example: "Job.run() is the scheduler's heartbeat — it checks whether the job's \
next run time has passed and fires the callable, then reschedules the next execution."

PURPOSE
2-3 sentences. What problem does this code solve? Why does it exist as a distinct \
unit rather than being inlined elsewhere? What would break or become harder without it?

HOW IT WORKS
3-5 numbered steps walking through the actual logic. Reference real variable names, \
branch conditions, and method calls from the code. Be specific about control flow, \
data transformations, and any state that changes.

NOTABLE
Anything a maintainer must know: which exceptions can propagate, mutable state that \
is modified, thread-safety assumptions, performance traps, surprising edge cases, or \
deferred work (TODOs, known limitations). If nothing is notable, write "None."\
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
        for c in callers:#[:5]:
            lines.append(f"{c.qualified_name}: {c.signature}")

    if callees:
        lines += ["", "--- CALLS ---"]
        for c in callees:#[:5]:
            lines.append(f"{c.qualified_name}: {c.signature}")

    return [
        {"role": "system", "content": _EXPLAIN_SYSTEM},
        {"role": "user",   "content": "\n".join(lines)},
    ]
