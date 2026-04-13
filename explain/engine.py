"""explain/engine.py

Two-mode explanation engine for code symbols.

Build mode  — pre-generates explanations and stores them in the DB silently.
              Run once (like `cex embed`) to warm the cache before querying.
              ``cex build`` / ``cex build --target <t>`` / ``cex build --fresh``

Query mode  — reads the cached explanation for a target and streams it to stdout.
              If no explanation exists yet, it generates one on-the-fly and caches
              it before printing.  ``cex explain <target>``

Target resolution (shared by both modes):
  1. Contains ``/`` or ends in ``.py`` → all top-level symbols in the file
  2. Exact qualified name match        → one symbol
  3. Anything else                     → semantic / keyword search, top result
"""

from config import LoggingConfig
from ingestion.database import DatabaseManager
from ingestion.models import SymbolModel
from llm.client import LLMClient
from llm.logger import log_prompt
from llm.prompts import build_explain_prompt
from search.retriever import Retriever


class ExplainEngine:
    def __init__(
        self,
        db: DatabaseManager,
        client: LLMClient,
        retriever: Retriever,
        log_cfg: LoggingConfig | None = None,
    ):
        self._db = db
        self._client = client
        self._retriever = retriever
        self._log_cfg = log_cfg or LoggingConfig()

    # ── Build mode ────────────────────────────────────────────────────────────

    def build(self, target: str, fresh: bool = False) -> None:
        """Pre-generate and cache explanations for a resolved target.

        LLM output is NOT streamed — only per-symbol progress lines are printed.
        Use ``query()`` afterwards to read the cached results interactively.

        ``fresh=True`` replaces existing cached explanations for the target.
        """
        symbols = self._resolve(target)
        if not symbols:
            print(f"No symbols found for: {target!r}")
            return

        total = len(symbols)
        for i, sym in enumerate(symbols, 1):
            if not fresh:
                cached = self._db.fetch_explanation(sym.qualified_name)
                if cached:
                    print(f"[{i}/{total}] {sym.qualified_name} (cached)")
                    continue

            print(f"[{i}/{total}] {sym.qualified_name} ...", end=" ", flush=True)
            self._generate(sym)
            print("done")

    def build_all(self, fresh: bool = False) -> None:
        """Pre-generate and cache explanations for every symbol in the DB.

        Skips symbols that already have a cached explanation (unless ``fresh=True``).
        Progress is printed to stdout; LLM output is suppressed to avoid noise.
        """
        symbols = self._db.fetch_all_symbols()
        total = len(symbols)
        cached_count = 0

        for i, sym in enumerate(symbols, 1):
            if not fresh and self._db.fetch_explanation(sym.qualified_name):
                cached_count += 1
                print(f"[{i}/{total}] {sym.qualified_name} (cached)")
                continue

            print(f"[{i}/{total}] {sym.qualified_name} ...", end=" ", flush=True)
            self._generate(sym)
            print("done")

        generated = total - cached_count
        print(f"\nBuild complete: {generated} generated, {cached_count} from cache.")

    # ── Query mode ────────────────────────────────────────────────────────────

    def query(self, target: str) -> None:
        """Print the explanation for a target, generating and caching it if needed.

        Cache hit:  the stored text is printed immediately — no LLM call.
        Cache miss: the LLM is called with streaming so output appears token by token,
                    then the result is saved to the DB for next time.
        """
        symbols = self._resolve(target)
        if not symbols:
            print(f"No symbols found for: {target!r}")
            return

        for sym in symbols:
            print(f"\n{'─' * 60}")
            print(f"  {sym.qualified_name}  [{sym.type}]")
            print(f"{'─' * 60}\n")

            cached = self._db.fetch_explanation(sym.qualified_name)
            if cached:
                print(cached)
            else:
                # Not in DB yet — generate with streaming so the user sees output
                # immediately, then cache the result for subsequent queries.
                self._generate(sym, stream=True)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve(self, target: str) -> list[SymbolModel]:
        """Resolve a target string to a list of SymbolModel instances.

        Tries three strategies in order (see module docstring).
        """
        # File path → top-level symbols (no parent class) for that file.
        if "/" in target or target.endswith(".py"):
            syms = self._retriever.get_by_file(target)
            top = [s for s in syms if not self._retriever.get_parent(s.qualified_name)]
            return top if top else syms

        # Exact qualified-name match.
        sym = self._retriever.get_by_id(target)
        if sym:
            return [sym]

        # Fall back to semantic / keyword search → return the single best result.
        results = self._retriever.search(target, k=3)
        return results[:1]

    def _generate(self, sym: SymbolModel, stream: bool = False) -> str:
        """Call the LLM for one symbol, log the prompt, and persist the result.

        ``stream=False`` (default): silent — for bulk build runs.
        ``stream=True``:  tokens printed to stdout as they arrive — for interactive query.
        """
        parent  = self._retriever.get_parent(sym.qualified_name)
        callers = self._retriever.get_callers(sym.qualified_name)
        callees = self._retriever.get_callees(sym.qualified_name)

        messages = build_explain_prompt(sym, parent, callers, callees)

        # Optionally write the full prompt to logs/prompts.log.
        log_prompt(messages, sym.qualified_name, self._log_cfg)

        result = self._client.chat(messages, stream=stream)
        self._db.save_explanation(sym.qualified_name, result)
        return result

