# cex — Explainer

Generates and caches LLM explanations for code symbols.

---

## Commands

```
cex explain <target>          # explain a specific symbol, file, or query
cex explain --all             # generate explanations for every symbol
cex explain <target> --fresh  # ignore cache, regenerate
cex explain --all --fresh     # regenerate everything
```

---

## Design Principles

**Cache everything.** LLM calls are slow on local hardware.  Every explanation is written to the `explanations` table immediately after generation.  Subsequent calls return the cached text without touching the LLM.

**Code doesn't change.** cex is designed for indexing a repo once and querying it many times.  Explanations are tied to the ingested snapshot.  If the repo changes, re-ingest and run `cex explain --all --fresh`.

---

## Target Resolution

`explain(target)` resolves the target in order:

| Target looks like | Action |
|---|---|
| Contains `/` or ends in `.py` | Fetch all top-level symbols (no parent class) in the file |
| Exact qualified name match | Explain that one symbol |
| Anything else | Semantic/keyword search → top result |

**Top-level symbols** for file explanation: symbols with no `NESTED_IN` parent — typically module-level classes and functions.  Methods are included via their parent class's `code_body`, so the LLM sees the full class context.

---

## Context Building

For each symbol, the following context is assembled before calling the LLM:

```
symbol.code_body          ← always included (full)
parent.signature          ← if the symbol is a method (1 line only)
callers[:5].signature     ← up to 5 callers, signatures only
callees[:5].signature     ← up to 5 callees, signatures only
```

Neighbours are **signatures only** — just enough for the LLM to know what interacts with this symbol, without wasting the context window on code the LLM doesn't need.

---

## Prompt Structure

```
[system]
You are a concise, precise code explainer. Reply with exactly these four sections:

SUMMARY: one sentence describing what this symbol is
PURPOSE: the problem it solves or role it plays
HOW IT WORKS: 3-5 numbered steps walking through the logic
NOTABLE: edge cases, exceptions raised, state mutations, or side effects

[user]
SYMBOL: schedule.__init__.Job.run  TYPE: function  FILE: schedule/__init__.py

--- CODE ---
def run(self):
    if self._is_overdue(datetime.datetime.now()):
        ...

--- PARENT ---
class Job(Scheduler)

--- CALLED BY ---
schedule.__init__.Scheduler._run_job: def _run_job(self, job: "Job") -> None

--- CALLS ---
schedule.__init__.Job._is_overdue: def _is_overdue(self, when: datetime.datetime)
schedule.__init__.Job._schedule_next_run: def _schedule_next_run(self) -> None
```

---

## Output Format

**Interactive** (`cex explain <target>`): LLM tokens are streamed to stdout as they arrive.  The response is also saved to the DB.

**Bulk** (`cex explain --all`): output is suppressed per-symbol; only a progress line is printed.  This prevents thousands of lines of LLM output flooding the terminal.  Use `cex explain <name>` afterwards to view any individual explanation.

---

## Caching

The `explanations` table stores one row per symbol:

```sql
id           TEXT PRIMARY KEY  -- = symbols.id (qualified_name)
text         TEXT NOT NULL
generated_at TIMESTAMPTZ DEFAULT now()
```

On `save_explanation`, an upsert updates the `generated_at` timestamp:

```sql
INSERT INTO explanations (id, text)
VALUES (%s, %s)
ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text, generated_at = now()
```

No FK to `symbols` — intentional.  Re-ingesting a repo replaces symbols rows but leaves existing explanations intact.

---

## ExplainEngine API

```python
engine = ExplainEngine(db, client, retriever)

engine.explain("Job.run")               # single symbol, streamed
engine.explain("schedule/__init__.py") # file — top-level symbols
engine.explain("how are jobs cancelled?") # semantic search → top result
engine.explain_all()                    # all symbols, progress only
engine.explain("Job.run", fresh=True)  # force regeneration
```
