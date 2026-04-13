# cex — Database Schema

All tables use human-readable **TEXT primary keys** derived from natural keys.  No UUIDs.  This eliminates DB round-trips in the ingestion engine and makes rows directly inspectable with `psql`.

---

## Table Map

```
files ──< symbols ──< relations
  │              └──> relations
  └──< file_imports

repo_info (standalone)
dependencies (standalone)
explanations (mirrors symbols.id)
```

---

## files

One row per source file discovered during ingestion.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Relative path from repo root, e.g. `schedule/__init__.py` |
| `extension` | TEXT | `.py`, `.ts`, … |
| `language` | TEXT | `python` (drives parser routing) |

---

## symbols

Every class, function, endpoint, or ORM model extracted by tree-sitter.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | `qualified_name`, e.g. `schedule.__init__.Scheduler.run_pending` |
| `file_id` | TEXT FK→files | Which file this symbol lives in |
| `type` | TEXT | `class` \| `function` \| `endpoint` \| `model` |
| `name` | TEXT | Bare name (e.g. `run_pending`) |
| `qualified_name` | TEXT | Full dotted path (same as `id`) |
| `signature` | TEXT | First source line of the definition |
| `code_body` | TEXT | Full source text of the symbol |
| `start_line` | INT | 1-based start line |
| `end_line` | INT | 1-based end line |
| `metadata` | JSONB | Type-specific extras: `is_async`, `decorators`, `bases`, `method` |
| `embedding` | VECTOR(N) | Added by `cex embed` — not in static DDL |

**Why store `code_body`?**  The LLM needs the full source to generate accurate explanations.  Storing it avoids re-reading files on every query and works even if the repo is moved or deleted after ingestion.

---

## relations

Directed edges between symbols.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | `{source_id}::{relation_type}::{target_id}` |
| `source_symbol_id` | TEXT FK→symbols | |
| `target_symbol_id` | TEXT FK→symbols | |
| `relation_type` | TEXT | `NESTED_IN` \| `CALLS` \| `IMPORTS` \| `ROUTES_TO` |

**Relation semantics:**

| Type | Source | Target | Meaning |
|---|---|---|---|
| `NESTED_IN` | parent | child | `Job.run` is nested in `Job` |
| `CALLS` | caller | callee | `Scheduler.run_pending` calls `Scheduler._run_job` |
| `IMPORTS` | file symbol | imported module | planned |
| `ROUTES_TO` | HTTP handler | target | planned |

**Composite PK**: `{src}::{type}::{tgt}` means duplicate edges are silently dropped by `ON CONFLICT DO NOTHING`.

---

## repo_info

One row per ingested repository root.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Absolute path to the repo root |
| `language` | TEXT | Primary language |
| `ingested_at` | TIMESTAMPTZ | Auto-set to `now()` on upsert |
| `metadata` | JSONB | Reserved for repo-level extras |

---

## dependencies

Packages detected from `requirements.txt` and `pyproject.toml`.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | `{manifest_file}::{name}` |
| `name` | TEXT | Package name |
| `version` | TEXT | Declared version constraint |
| `manifest_file` | TEXT | `requirements.txt` or `pyproject.toml` |
| `language` | TEXT | `python` |

---

## file_imports

Module-level import statements parsed from each source file.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | `{file_id}::{module}` |
| `file_id` | TEXT FK→files | Which file contains the import |
| `module` | TEXT | Imported module name, e.g. `datetime` |
| `names` | TEXT[] | What was imported: `['timedelta', 'timezone']`; empty for bare `import os` |

Used by the future Flow Tracer to follow cross-file dependency chains.

---

## explanations

Cached LLM-generated explanations for symbols.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Same as `symbols.id` (qualified_name) |
| `text` | TEXT | Full LLM response |
| `generated_at` | TIMESTAMPTZ | Last generation time |

No FK to `symbols` — intentional.  Re-ingesting a repo replaces symbols but keeps explanations; use `cex explain --all --fresh` to regenerate.

---

## Embedding Column (dynamic)

The `embedding VECTOR(N)` column on `symbols` is added by `cex embed`, not in the static DDL.  `N` comes from `config.toml → llm.embed_dim`.  This keeps the schema model-agnostic.

```sql
-- Added by EmbeddingEngine._ensure_column()
ALTER TABLE symbols ADD COLUMN IF NOT EXISTS embedding VECTOR(768);
CREATE INDEX IF NOT EXISTS symbols_embedding_idx
    ON symbols USING hnsw (embedding vector_cosine_ops);
```
