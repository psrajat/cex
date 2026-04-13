# cex — Search (Embeddings + Retrieval)

Provides semantic and keyword search over ingested symbols.

---

## Commands

```
cex embed [--force]   →  EmbeddingEngine.run()
```

---

## EmbeddingEngine (`search/embeddings.py`)

### What it does

1. Adds the `embedding VECTOR(N)` column to `symbols` if it doesn't exist yet (idempotent `ALTER TABLE`)
2. Creates an HNSW index for fast cosine similarity queries
3. Fetches all symbols with `embedding IS NULL` (or all symbols with `--force`)
4. Batches them in groups of 32 and calls `LLMClient.embed()`
5. Updates each symbol with its vector via `UPDATE symbols SET embedding = %s::vector WHERE id = %s`

### Why ALTER TABLE instead of DDL

The vector dimension `N` depends on the embedding model (`embed_dim` in config).  Hardcoding it in `setup_db.py` would break when switching models.  `ALTER TABLE ADD COLUMN IF NOT EXISTS` is idempotent and model-aware.

### What is embedded

```python
f"{symbol.qualified_name}\n{symbol.signature}\n{symbol.code_body[:1500]}"
```

- Leading with `qualified_name` and `signature` ensures the most identifiable tokens are early (embedding models weight early tokens more heavily).
- Body is capped at 1500 characters to stay within embedding model context limits.

### Incremental embedding

Running `cex embed` again only embeds symbols added since the last run (`WHERE embedding IS NULL`).  Use `--force` to re-embed everything (e.g., after switching models).

---

## Retriever (`search/retriever.py`)

The shared query layer used by the Explainer (and the future Tracer).  No raw SQL outside this class and `DatabaseManager`.

### Methods

| Method | Description |
|---|---|
| `get_by_id(id)` | Fetch a single symbol by qualified name |
| `get_by_file(file_id)` | All symbols in a file, ordered by line |
| `get_callees(id)` | Symbols that `id` calls (outgoing CALLS edges) |
| `get_callers(id)` | Symbols that call `id` (incoming CALLS edges) |
| `get_parent(id)` | Enclosing symbol (NESTED_IN source) |
| `search(query, k=10)` | Semantic or keyword search |

### Search strategy

`search()` tries vector search first.  If the query embedding call fails (e.g., LLM server down, no embeddings yet), it falls back to `ILIKE` keyword search automatically.  The explainer therefore works before `cex embed` has been run.

**Vector search**: embeds the query string, issues:
```sql
SELECT ... FROM symbols
WHERE embedding IS NOT NULL
ORDER BY embedding <=> %s::vector
LIMIT %s
```

**Keyword search** (fallback):
```sql
SELECT ... FROM symbols
WHERE name ILIKE %s OR qualified_name ILIKE %s
ORDER BY name LIMIT %s
```

### Graph traversal

`get_callees` / `get_callers` / `get_parent` each do a single JOIN query:
```sql
SELECT s.*
FROM   relations r
JOIN   symbols   s ON s.id = r.<join_col>
WHERE  r.<filter_col> = %s AND r.relation_type = %s
```

This is O(1) DB calls per hop — no iterative lookups.
