# cex — Ingestion Pipeline

Transforms a source repository into a structured PostgreSQL graph of files, symbols, and relations.

---

## Entry Point

```
cex ingest <repo_dir>
```

Runs `IngestionEngine(repo_dir, db_config).run()`.

---

## Pipeline Stages

```
repo dir
  │
  ├─ parse_manifests()  →  DependencyModel[]  →  insert_dependencies()
  │
  └─ parse_files()      →  FileModel[]        →  insert_files()
       │
       └─ for each file:
            parse_symbols_and_relations(file)
              │
              ├─ symbols[]   →  batch_insert_symbols()
              ├─ relations[] →  batch_insert_relations()
              └─ imports[]   →  insert_file_imports()
```

All inserts use `ON CONFLICT (id) DO NOTHING` — re-ingesting the same repo is safe.

---

## Language Registry (`_LANG_SPECS`)

Adding a new language requires only a new entry in `_LANG_SPECS` in `parser.py`.  No other code changes.

Each `LangSpec` is a frozen dataclass holding:

| Field | Purpose |
|---|---|
| `ts_parser` | tree-sitter `Parser` instance wired to the language |
| `lang` | Display name (`python`, `typescript`, …) |
| `file_glob` | Which files to pick up (`*.py`, `*.ts`, …) |
| `symbol_types` | AST node types that become `SymbolModel` rows |
| `call_type` | AST node type for function calls |
| `import_types` | AST node types for import statements |
| `get_name` | Extracts the symbol name from a node |
| `classify` | Returns `(type_str, metadata_dict)` for a node |
| `get_callee` | Extracts the callee name from a call node |
| `parse_import` | Returns `(module, [names])` from an import node |
| `module_prefix` | Converts a file path to a dotted module prefix |

---

## Symbol Parsing (`parse_symbols_and_relations`)

Single-pass over the tree-sitter AST per file.  Returns `(symbols, relations, imports)`.

**Pre-pass** — builds a `name → qualified_name` map for CALLS resolution.  The outermost definition wins when the same name appears in multiple scopes (accurate enough for intra-file call graphs in v1).

**Main walk** — depth-first:
- `symbol_types` nodes → emit `SymbolModel` + `NESTED_IN` edge to parent
- `call_type` nodes inside a function → emit `CALLS` edge using the pre-built map
- `import_types` nodes → emit import tuple

**Qualified names** are computed from the module prefix (e.g. `schedule.__init__`) + dotted path through parent scopes.  They are used as TEXT PKs in the DB.

---

## What is NOT indexed

- Variables and constants — they live inside a symbol's `code_body` and are provided as LLM context, not queried directly.
- Test files — excluded via `_SKIP_DIRS` and `_TEST_FILE_RE`.  Tests explain behaviour, not the code itself.
- Files in `venv`, `.venv`, `__pycache__`, `.git`, `node_modules`, `tests`, `test` directories.

---

## Symbol Types

| Type | Detected by |
|---|---|
| `class` | `class_definition` AST node |
| `function` | `function_definition` AST node (includes methods) |
| `endpoint` | `function` with HTTP decorator (`@app.get`, `@router.post`, etc.) |
| `model` | `class` inheriting from a known ORM base (`Base`, `Model`, etc.) |

`endpoint` and `model` are classified via `classify()` in the `LangSpec`.

---

## Relation Types

| Type | How detected |
|---|---|
| `NESTED_IN` | Parent node is a symbol type when walking the AST |
| `CALLS` | `call` node inside a function body; callee resolved via pre-pass map |
| `IMPORTS` | `import_statement` / `import_from_statement` nodes |
| `ROUTES_TO` | Planned — requires cross-file resolution |

---

## DatabaseManager

Thin psycopg2 wrapper.  `autocommit = True` — each statement is immediately durable.

Key methods used by the ingestion engine:

| Method | Description |
|---|---|
| `insert_files` | Bulk upsert file rows |
| `batch_insert_symbols` | Bulk upsert symbol rows |
| `batch_insert_relations` | Bulk upsert relation rows |
| `insert_file_imports` | Bulk upsert import rows |
| `fetch_symbol` / `fetch_symbols_by_file` | Read methods used by Retriever + Explainer |
| `fetch_related_symbols` | One-hop graph traversal (CALLS / NESTED_IN) |
| `update_embeddings` | Used by EmbeddingEngine |
| `vector_search` / `keyword_search` | Used by Retriever |
| `fetch_explanation` / `save_explanation` | Used by ExplainEngine |
