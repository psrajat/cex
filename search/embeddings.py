"""search/embeddings.py

Generates and stores vector embeddings for every symbol in the DB.

The ``embedding VECTOR(N)`` column and its HNSW index are created by
``setup_db.setup_database()`` during ``cex setup``, so this module never
issues schema-altering statements — it only reads and writes data.

Usage:
    engine = EmbeddingEngine(db, client, embed_cfg)
    engine.run()           # skip already-embedded symbols
    engine.run(force=True) # re-embed everything
"""

from config import EmbedConfig
from ingestion.database import DatabaseManager
from llm.client import LLMClient


class EmbeddingEngine:
    """Encodes all symbols in the database as dense vector embeddings.

    Symbols are embedded in configurable batches (``EmbedConfig.batch_size``)
    to balance memory use and network round-trips to the embedding server.
    Progress is printed to stdout so long-running bulk runs are observable.
    """

    def __init__(self, db: DatabaseManager, client: LLMClient, embed_cfg: EmbedConfig):
        self._db = db
        self._client = client
        self._cfg = embed_cfg

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, force: bool = False) -> None:
        """Embed all symbols and persist the vectors.

        ``force=False`` (default): only symbols whose ``embedding`` column is
        NULL are processed — safe to interrupt and resume.
        ``force=True``: re-embeds every symbol regardless of existing vectors.
        """
        symbols = self._db.fetch_symbols_for_embedding(force=force)

        if not symbols:
            print("All symbols already embedded. Use --force to re-embed.")
            return

        total = len(symbols)
        embedded = 0
        batch_size = self._cfg.batch_size

        for i in range(0, total, batch_size):
            batch = symbols[i : i + batch_size]

            # Build the text representation: qualified name first so the model
            # sees the most disambiguating signal at the start of the sequence.
            texts = [
                f"{s.qualified_name}\n{s.signature}\n{s.code_body[:1500]}"
                for s in batch
            ]

            vectors = self._client.embed(texts)
            self._db.update_embeddings(
                list(zip(vectors, [s.qualified_name for s in batch]))
            )
            embedded += len(batch)
            print(f"  Embedded {embedded}/{total}")

        print(f"\nDone. {total} symbols embedded.")
