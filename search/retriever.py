"""search/retriever.py

Shared query layer used by the Explainer (and future Tracer).

Resolves symbols by ID, file, or natural-language query.  Vector search is
used when embeddings are available; falls back to keyword search otherwise —
so the explainer works even before `cex embed` has been run.
"""

from ingestion.database import DatabaseManager
from ingestion.models import SymbolModel
from llm.client import LLMClient


class Retriever:
    def __init__(self, db: DatabaseManager, client: LLMClient):
        self._db = db
        self._client = client

    # ── Symbol lookup ─────────────────────────────────────────────────────────

    def get_by_id(self, symbol_id: str) -> SymbolModel | None:
        return self._db.fetch_symbol(symbol_id)

    def get_by_file(self, file_id: str) -> list[SymbolModel]:
        return self._db.fetch_symbols_by_file(file_id)

    # ── Neighbourhood traversal ───────────────────────────────────────────────

    def get_callees(self, symbol_id: str) -> list[SymbolModel]:
        """Symbols that symbol_id CALLS."""
        return self._db.fetch_related_symbols(symbol_id, "CALLS", direction="out")

    def get_callers(self, symbol_id: str) -> list[SymbolModel]:
        """Symbols that call symbol_id."""
        return self._db.fetch_related_symbols(symbol_id, "CALLS", direction="in")

    def get_parent(self, symbol_id: str) -> SymbolModel | None:
        """Enclosing class/function (NESTED_IN source)."""
        # NESTED_IN: source=parent, target=child  →  incoming edge to symbol_id
        parents = self._db.fetch_related_symbols(symbol_id, "NESTED_IN", direction="in")
        return parents[0] if parents else None

    # ── Semantic search ───────────────────────────────────────────────────────

    def search(self, query: str, k: int = 10) -> list[SymbolModel]:
        """Return the k most relevant symbols for a natural-language query.

        Tries vector search first (requires `cex embed` to have been run).
        Falls back to ILIKE keyword search if no embeddings exist yet.
        """
        try:
            vec = self._client.embed([query])[0]
            results = self._db.vector_search(vec, k)
            if results:
                return results
        except Exception:
            pass
        return self._db.keyword_search(query, k)
