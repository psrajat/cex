## Plan: cex v1 — Code EXplainer Full Feature Build

**TL;DR:** Extend the existing ingestion pipeline (tree-sitter → PostgreSQL) into a 3-feature local-first code explainer. A new `llm/` module wraps any OpenAI-compatible server. pgvector (already in Docker) drives semantic retrieval. `httpx` + `rich` are the only two new deps.

---

**Phase 0 — Bug fixes + Schema (blocks everything)**
1. setup_db.py: add `UNIQUE(path)` to `files` DDL (fixes broken `ON CONFLICT`)
2. setup_db.py: fix bare second connection (missing credentials)
3. setup_db.py: add `CREATE EXTENSION IF NOT EXISTS vector;`
4. database.py: implement both `insert_auls()` and `insert_relations()` stubs (they're currently `pass`)
5. main.py: pass `DBConfig` dataclass to `IngestionEngine` instead of a plain `dict`

**Phase 1 — Extend Parser** *(parallel with Phase 2; blocks Phase 5)*

6. parser.py: add `parse_imports()` — tree-sitter `import_statement`/`import_from_statement` → `RelationModel` with `IMPORTS`
7. parser.py: add `parse_calls()` — tree-sitter `call` nodes inside function bodies → `RelationModel` with `CALLS`
8. engine.py: integrate both into the per-file loop

**Phase 2 — LLM Client + Config** *(parallel with Phase 1; blocks Phases 3–6)*

9. config.toml + config.py: add `[llm]` section — `base_url`, `chat_model`, `embedding_model`, `api_key`, `embedding_dim`
10. `llm/client.py` — `LLMClient` using `httpx.AsyncClient`, two methods: `async chat(messages, system_prompt)` and `async embed(text)` pointing at OpenAI-compatible `/chat/completions` + `/embeddings`
11. `llm/prompts.py` — pure-function prompt builders: `explain_aul_prompt`, `answer_question_prompt`, `trace_flow_prompt`, `pr_suggestions_prompt`, `pr_diff_prompt`

**Phase 3 — Embeddings + Vector Search** *(depends on Phase 0 + 2; blocks Phases 4–6)*

12. setup_db.py: add `embedding VECTOR(N)` + HNSW index to `auls`; add 4 new tables: `explanations`, `use_case_flows`, `pr_suggestions`, `pr_changes`
13. `search/embeddings.py` — `EmbeddingEngine.generate_all()`: batches all un-embedded AULs through `LLMClient.embed()`, updates DB
14. `search/retriever.py` — `Retriever.find_relevant_auls(query, limit)`: embeds query, cosine similarity via `<=>` pgvector operator
15. main.py: add `cex embed` subcommand

**Phase 4 — Explainer** *(depends on Phase 3)*

16. `explain/engine.py` — `ExplainerEngine`:
    - `generate_all()`: for each AUL, fetches `NESTED_IN` context → `explain_aul_prompt` → stores in `explanations`
    - `ask(question)`: semantic retrieval → fetch stored explanations → `answer_question_prompt` → returns answer
17. main.py: add `cex explain generate` and `cex explain ask <query>`

**Phase 5 — Data Flow Tracer** *(depends on Phase 1 + 3)*

18. `trace/engine.py` — `FlowTracer.trace(use_case)`: semantic entry-point search → BFS/DFS via `CALLS`/`IMPORTS` relations → LLM traces narrative → stored in `use_case_flows`
19. main.py: add `cex trace <use_case>`, `cex trace list`, `cex trace show <name>`

**Phase 6 — PR Generator** *(depends on Phase 3 + 4)*

20. `pr/engine.py` — `PREngine`:
    - `suggest(request)`: semantic search → LLM returns **3 options (easy/medium/hard) as JSON** → stored in `pr_suggestions` + `pr_changes`
    - `generate_diff(change_id)`: fetch stored change → `pr_diff_prompt` requesting **unified diff with inline explanation comments** → stores diff back
21. `pr/differ.py` — `DiffFormatter`: `format_patch()` returns raw unified diff; `format_side_by_side()` renders with `rich`
22. main.py: add `cex pr suggest <description>`, `cex pr diff <change_id> [--format patch|side-by-side]`

**Phase 7 — Tests** *(parallel with Phases 4–6)*

23. 7 test files in `tests/`: `test_llm_client.py`, `test_parser_relations.py`, `test_embeddings.py`, `test_explainer.py`, `test_tracer.py`, `test_pr_engine.py`, `test_differ.py` — all LLM calls mocked with `unittest.mock`

---

**Relevant Files**

- setup_db.py — schema DDL; add UNIQUE, pgvector, 4 new tables, embedding column
- config.py + config.toml — `LLMConfig` dataclass + `[llm]` section
- main.py — all new CLI subcommands
- parser.py — `parse_imports()`, `parse_calls()`
- database.py — fill stubs; new insert methods
- New: `llm/`, `search/`, `explain/`, `trace/`, `pr/` modules, `tests/`

**New Deps:** `httpx>=0.27.0`, `rich>=13.0.0`

---

**Verification**
1. `uv run pytest` — all tests pass
2. `uv run python -m cex setup` — tables created; `\d auls` shows `embedding vector(768)`
3. `uv run python -m cex ingest test_projects/schedule` — ingests; `relations` has `CALLS`/`IMPORTS` rows
4. `uv run python -m cex embed` — all AULs have non-null embeddings
5. `uv run python -m cex explain generate` + `cex explain ask "What does the scheduler do?"`
6. `uv run python -m cex trace "Schedule a job to run every hour"` — stored in `use_case_flows`
7. `uv run python -m cex pr suggest "Add async support to job execution"` — 3 options shown
8. `uv run python -m cex pr diff <id> --format patch` — valid unified diff

---

**Decisions**
- OpenAI-compatible API (works with Ollama, LocalAI, llama.cpp)
- Python-only parsing in v1
- `difflib` (stdlib) for diff validation; LLM generates the actual diff text
- Structured JSON output from LLM for PR suggestions
- All LLM I/O is `async`; CLI uses `asyncio.run()`
- **Out of scope:** non-Python repos, GitHub API, auth, web UI, streaming