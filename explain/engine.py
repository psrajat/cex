"""explain/engine.py

Generates and caches LLM explanations for code symbols.

Explanations are stored in the `explanations` table (id = symbol qualified_name)
and reused on subsequent calls.  The assumption is that ingested code doesn't
change — if you re-ingest a repo, run `cex explain --all --fresh` to regenerate.

Entry-point resolution for `explain(target)`:
  1. Path ending in .py or containing /  → explain all top-level symbols in the file
  2. Exact qualified name (e.g. "Job.run" or "schedule.__init__.Job.run") → one symbol
  3. Anything else → semantic/keyword search, top result
"""

from ingestion.database import DatabaseManager
from ingestion.models import SymbolModel
from llm.client import LLMClient
from llm.prompts import build_explain_prompt
from search.retriever import Retriever


class ExplainEngine:
    def __init__(self, db: DatabaseManager, client: LLMClient, retriever: Retriever):
        self._db = db
        self._client = client
        self._retriever = retriever

    # ── Public commands ───────────────────────────────────────────────────────

    def explain(self, target: str, fresh: bool = False) -> None:
        """Explain a target (file path, qualified name, or free-text query).

        Results are printed to stdout (streaming) and cached in the DB.
        """
        symbols = self._resolve(target)
        if not symbols:
            print(f"No symbols found for: {target!r}")
            return

        for sym in symbols:
            print(f"\n{'─' * 60}")
            print(f"  {sym.qualified_name}  [{sym.type}]")
            print(f"{'─' * 60}\n")
            self._explain_symbol(sym, fresh=fresh, stream=True)

    def explain_all(self, fresh: bool = False) -> None:
        """Generate and cache explanations for every symbol in the DB.

        Progress is printed to stdout; LLM output is NOT streamed (too noisy
        for bulk runs).  Use `explain <target>` to view a specific explanation.
        """
        symbols = self._db.fetch_all_symbols()
        total = len(symbols)
        cached_count = 0

        for i, sym in enumerate(symbols, 1):
            cached = self._db.fetch_explanation(sym.qualified_name)
            if cached and not fresh:
                cached_count += 1
                print(f"[{i}/{total}] {sym.qualified_name} (cached)")
                continue

            print(f"[{i}/{total}] {sym.qualified_name} ...", end=" ", flush=True)
            self._explain_symbol(sym, fresh=True, stream=False)
            print("done")

        generated = total - cached_count
        print(f"\nExplanations: {generated} generated, {cached_count} from cache.")

    # ── Private ───────────────────────────────────────────────────────────────

    def _resolve(self, target: str) -> list[SymbolModel]:
        # File path → top-level symbols (symbols with no parent class)
        if "/" in target or target.endswith(".py"):
            syms = self._retriever.get_by_file(target)
            top = [s for s in syms if not self._retriever.get_parent(s.qualified_name)]
            return top if top else syms

        # Exact qualified-name match
        sym = self._retriever.get_by_id(target)
        if sym:
            return [sym]

        # Partial name match before falling back to semantic search
        # e.g. "Job.run" might not be the full qname but is close
        results = self._retriever.search(target, k=3)
        return results[:1]

    def _explain_symbol(
        self, sym: SymbolModel, fresh: bool, stream: bool
    ) -> str:
        """Generate (or retrieve from cache) an explanation for one symbol.

        Cache hit: returned / printed immediately without an LLM call.
        Cache miss: LLM is called, result is persisted in `explanations`, then returned.
        ``fresh=True`` bypasses the cache check and always calls the LLM.
        """
        if not fresh:
            cached = self._db.fetch_explanation(sym.qualified_name)
            if cached:
                if stream:
                    print(cached)
                return cached

        # Gather 1-hop neighbourhood for context (signatures only, not full bodies).
        parent = self._retriever.get_parent(sym.qualified_name)
        callers = self._retriever.get_callers(sym.qualified_name)
        callees = self._retriever.get_callees(sym.qualified_name)

        messages = build_explain_prompt(sym, parent, callers, callees)
        result = self._client.chat(messages, stream=stream)

        # Persist so future calls for this symbol skip the LLM.
        self._db.save_explanation(sym.qualified_name, result)
        return result
