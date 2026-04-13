# cex — Explainer

Generates and caches LLM explanations for code symbols.

---

## Two-step mental model

```
cex build   →  generate explanations, store in DB, no output displayed
cex explain →  read from DB, generate on-demand if missing, stream to stdout
```

Think of `cex build` the same way as `cex embed`: run it once after ingestion to
pre-populate the cache.  `cex explain` is then instant (DB read) for anything
already built, or transparent (LLM call → cache → display) for anything new.

---

## Commands

```
# Pre-build explanations (no LLM output shown, just progress)
cex build                        # build every symbol in the DB
cex build schedule/__init__.py   # build all top-level symbols in a file
cex build "Job.run"              # build one symbol by qualified name
cex build "how jobs are cancelled" # build top search result
cex build --fresh                # rebuild everything, ignoring cache
cex build "Job.run" --fresh      # rebuild one symbol

# Query explanations (streams to stdout; generates if not yet cached)
cex explain "Job.run"
cex explain schedule/__init__.py
cex explain "how does the scheduler handle time zones"
```

---

## Design Principles

**Separate generation from display.**  `build` and `query` do one thing each.
`build` is a background batch job; `query` is an interactive reader.

**Cache everything.**  LLM calls are slow on local hardware.  Every explanation
is written to the `explanations` table immediately after generation.  Subsequent
`explain` calls return the cached text without touching the LLM.

**Lazy generation in query mode.**  If you call `cex explain` on a symbol that
hasn't been built yet, the engine generates it on the spot, caches it, and streams
it to stdout — no need to run `cex build` first.

---

## Target Resolution

Both `build` and `query` use the same resolver, which tries three strategies in order:

| Target form | Action |
|---|---|
| Contains `/` or ends in `.py` | All top-level symbols (no parent class) in the file |
| Exact qualified name | That one symbol |
| Anything else | Semantic / keyword search → top result |

**Top-level symbols** for file targets: symbols with no `NESTED_IN` parent — typically
module-level classes and functions.  Methods are accessible via `cex explain ClassName.method`.

---

## Context Building

For each symbol the engine assembles:

```
symbol.code_body          ← full source (always included)
parent.signature          ← if the symbol is a method/nested function (1 line)
callers.signature         ← all callers, signatures only
callees.signature         ← all callees, signatures only
```

Neighbours are **signatures only** — enough for the LLM to understand the call context
without filling the context window with bodies it doesn't need.

---

## Output Format

**`cex explain <target>`** — tokens streamed to stdout as they arrive.  Result cached.

**`cex build` / `cex build <target>`** — LLM output suppressed; only progress lines printed:

```
[1/64] schedule.__init__.Scheduler ...  done
[2/64] schedule.__init__.Job ...  done
[3/64] schedule.__init__.Job.run (cached)
...
Build complete: 61 generated, 3 from cache.
```

---

## Caching

The `explanations` table stores one row per symbol:

```sql
id           TEXT PRIMARY KEY  -- = symbols.id (qualified_name)
text         TEXT NOT NULL
generated_at TIMESTAMPTZ DEFAULT now()
```

`save_explanation` upserts — re-running `cex build --fresh` replaces the text and
updates `generated_at`.  No FK to `symbols` is intentional: re-ingesting a repo
replaces symbol rows but leaves expensive LLM output intact.

---

## ExplainEngine API

```python
engine = ExplainEngine(db, client, retriever)

# Build mode — generate and cache, no streaming
engine.build_all()                     # all symbols
engine.build_all(fresh=True)           # force-regenerate all
engine.build("Job.run")               # one symbol
engine.build("schedule/__init__.py")  # file — top-level symbols
engine.build("Job.run", fresh=True)   # force-regenerate one

# Query mode — read from DB, lazy-generate if missing, stream to stdout
engine.query("Job.run")
engine.query("schedule/__init__.py")
engine.query("how are jobs scheduled")
```

---

## Target Resolution

Both `build` and `query` use the same resolver
