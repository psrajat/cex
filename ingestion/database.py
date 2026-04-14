import json
import psycopg2
from psycopg2 import extras
from .models import DependencyModel, FileModel, SymbolModel

# Column list used by every symbol SELECT — order must match _row_to_symbol().
_SYMBOL_COLS = (
    "id, file_id, type, name, qualified_name, "
    "signature, code_body, start_line, end_line, metadata"
)


class DatabaseManager:
    """Thin wrapper around a psycopg2 connection for all cex database operations.

    All primary keys are human-readable TEXT derived from natural keys:
      files.id        = relative file path        ('schedule/__init__.py')
      symbols.id      = qualified_name             ('schedule.__init__.Scheduler')
      relations.id    = '{src}::{type}::{tgt}'
      dependencies.id = '{manifest_file}::{name}'
      file_imports.id = '{file_id}::{module}'

    The connection is opened with ``autocommit=True`` so each statement is
    committed immediately — no explicit transaction management required.
    Schema DDL is handled exclusively by ``setup_db.setup_database()``.
    """

    def __init__(self, db_config):
        # db_config must be a DBConfig dataclass (host, name, user, password).
        self.config = db_config
        self.conn = None
        self.cur = None

    def connect(self) -> None:
        self.conn = psycopg2.connect(
            host=self.config.host,
            dbname=self.config.name,
            user=self.config.user,
            password=self.config.password,
        )
        self.conn.autocommit = True
        self.cur = self.conn.cursor()

    def close(self) -> None:
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    # ── Idempotent inserts ────────────────────────────────────────────────────

    def insert_dependencies(self, dependencies: list[DependencyModel]) -> None:
        """Insert manifest-level package dependencies, skipping duplicates."""
        if not dependencies:
            return
        extras.execute_values(
            self.cur,
            "INSERT INTO dependencies (id, language, name, version, manifest_file)"
            " VALUES %s ON CONFLICT (id) DO NOTHING",
            [(f"{d.manifest_file}::{d.name}", d.language, d.name, d.version, d.manifest_file)
             for d in dependencies],
        )

    def insert_files(self, files: list[FileModel]) -> None:
        """Insert source file records, skipping files already in the DB."""
        if not files:
            return
        extras.execute_values(
            self.cur,
            "INSERT INTO files (id, extension, language)"
            " VALUES %s ON CONFLICT (id) DO NOTHING",
            [(f.path, f.extension, f.language) for f in files],
        )

    def upsert_repo_info(self, root_path: str, language: str) -> None:
        """Insert or refresh the repo_info row for this repository."""
        self.cur.execute(
            "INSERT INTO repo_info (id, language)"
            " VALUES (%s, %s)"
            " ON CONFLICT (id)"
            " DO UPDATE SET language = EXCLUDED.language, ingested_at = now()",
            (root_path, language),
        )

    def fetch_repo_info(self) -> dict | None:
        """Return the repo_info row as a dict, or None."""
        self.cur.execute("SELECT id, language, ingested_at, metadata FROM repo_info LIMIT 1")
        row = self.cur.fetchone()
        if not row:
            return None
        return {
            "root": row[0],
            "language": row[1],
            "ingested_at": row[2],
            "metadata": row[3],
        }

    def fetch_all_dependencies(self) -> list[DependencyModel]:
        """Return all package dependencies discovered during ingestion."""
        self.cur.execute("SELECT name, version, manifest_file, language FROM dependencies ORDER BY name")
        return [
            DependencyModel(name=r[0], version=r[1], manifest_file=r[2], language=r[3])
            for r in self.cur.fetchall()
        ]

    # ── Batch inserts ─────────────────────────────────────────────────────────

    def batch_insert_symbols(self, symbols: list[tuple]) -> None:
        """Insert symbols extracted from a single source file.

        Each tuple must be:
        (id, file_id, type, name, qualified_name, signature, code_body,
         start_line, end_line, metadata_json_str)

        ON CONFLICT DO NOTHING: re-ingesting the same file is safe.
        """
        if not symbols:
            return
        extras.execute_values(
            self.cur,
            "INSERT INTO symbols"
            " (id, file_id, type, name, qualified_name, signature, code_body,"
            "  start_line, end_line, metadata)"
            " VALUES %s ON CONFLICT (id) DO NOTHING",
            symbols,
        )

    def batch_insert_relations(self, relations: list[tuple]) -> None:
        """Insert directed edges between symbols.

        Each tuple must be:
        (id, source_symbol_id, target_symbol_id, relation_type)
        """
        if not relations:
            return
        extras.execute_values(
            self.cur,
            "INSERT INTO relations (id, source_symbol_id, target_symbol_id, relation_type)"
            " VALUES %s ON CONFLICT (id) DO NOTHING",
            relations,
        )

    def insert_file_imports(self, file_id: str, imports: list[tuple[str, list[str]]]) -> None:
        """Insert module-level import statements for a source file.

        ``imports``: list of (module_name, [imported_names]) tuples as returned
        by ``CodeParser.parse_symbols_and_relations()``.
        psycopg2 converts Python lists to TEXT[] automatically.
        """
        if not imports:
            return
        extras.execute_values(
            self.cur,
            "INSERT INTO file_imports (id, file_id, module, names) VALUES %s ON CONFLICT (id) DO NOTHING",
            [(f"{file_id}::{module}", file_id, module, names) for module, names in imports],
        )

    # ── Symbol queries ────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_symbol(row: tuple) -> SymbolModel:
        """Map a raw DB row (in _SYMBOL_COLS order) to a SymbolModel."""
        id_, file_id, type_, name, qname, sig, body, sl, el, meta = row
        return SymbolModel(
            file_path=file_id,
            qualified_name=qname,
            type=type_,
            name=name,
            signature=sig or "",
            code_body=body or "",
            start_line=sl or 0,
            end_line=el or 0,
            metadata=meta if isinstance(meta, dict) else {},
        )

    def fetch_symbol(self, symbol_id: str) -> SymbolModel | None:
        """Look up a single symbol by its qualified name (id)."""
        self.cur.execute(f"SELECT {_SYMBOL_COLS} FROM symbols WHERE id = %s", (symbol_id,))
        row = self.cur.fetchone()
        return self._row_to_symbol(row) if row else None

    def fetch_symbols_by_file(self, file_id: str) -> list[SymbolModel]:
        """Return all symbols in a file, ordered by source line."""
        self.cur.execute(
            f"SELECT {_SYMBOL_COLS} FROM symbols WHERE file_id = %s ORDER BY start_line",
            (file_id,),
        )
        return [self._row_to_symbol(r) for r in self.cur.fetchall()]

    def fetch_all_symbols(self) -> list[SymbolModel]:
        """Return every symbol in the DB, ordered by file then line."""
        self.cur.execute(
            f"SELECT {_SYMBOL_COLS} FROM symbols ORDER BY file_id, start_line"
        )
        return [self._row_to_symbol(r) for r in self.cur.fetchall()]

    def fetch_symbols_for_embedding(self, force: bool = False) -> list[SymbolModel]:
        """Return symbols that need embedding.

        ``force=False``: only symbols whose embedding column is NULL.
        ``force=True``:  all symbols (re-embed everything).

        The embedding column is guaranteed to exist after ``cex setup``
        because ``setup_db.setup_database()`` creates it.
        """
        if force:
            return self.fetch_all_symbols()
        self.cur.execute(
            f"SELECT {_SYMBOL_COLS} FROM symbols "
            "WHERE embedding IS NULL ORDER BY file_id, start_line"
        )
        return [self._row_to_symbol(r) for r in self.cur.fetchall()]

    def fetch_related_symbols(
        self, symbol_id: str, relation_type: str, direction: str = "out"
    ) -> list[SymbolModel]:
        """Traverse one hop of the relation graph.

        direction='out': source=symbol_id → returns target symbols (e.g. callees).
        direction='in':  target=symbol_id → returns source symbols (e.g. callers).
        """
        if direction == "out":
            join_col, filter_col = "target_symbol_id", "source_symbol_id"
        else:
            join_col, filter_col = "source_symbol_id", "target_symbol_id"

        self.cur.execute(
            f"SELECT s.id, s.file_id, s.type, s.name, s.qualified_name, "
            f"s.signature, s.code_body, s.start_line, s.end_line, s.metadata "
            f"FROM relations r JOIN symbols s ON s.id = r.{join_col} "
            f"WHERE r.{filter_col} = %s AND r.relation_type = %s",
            (symbol_id, relation_type),
        )
        return [self._row_to_symbol(r) for r in self.cur.fetchall()]

    # ── Embedding operations ──────────────────────────────────────────────────

    def update_embeddings(self, pairs: list[tuple[list[float], str]]) -> None:
        """Persist embedding vectors for a batch of symbols.

        ``pairs``: list of (vector, symbol_id) tuples.
        The vector is serialised to the ``[x,y,z,...]`` format expected by pgvector.
        """
        for vec, sym_id in pairs:
            vec_str = "[" + ",".join(str(x) for x in vec) + "]"
            self.cur.execute(
                "UPDATE symbols SET embedding = %s::vector WHERE id = %s",
                (vec_str, sym_id),
            )

    def vector_search(self, embedding: list[float], k: int) -> list[SymbolModel]:
        """Return the k nearest symbols by cosine distance to ``embedding``."""
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        self.cur.execute(
            f"SELECT {_SYMBOL_COLS} FROM symbols "
            "WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec_str, k),
        )
        return [self._row_to_symbol(r) for r in self.cur.fetchall()]

    def keyword_search(self, query: str, limit: int = 10) -> list[SymbolModel]:
        """Case-insensitive substring search over symbol names.

        Used as a fallback when no embeddings exist yet.
        """
        self.cur.execute(
            f"SELECT {_SYMBOL_COLS} FROM symbols "
            "WHERE name ILIKE %s OR qualified_name ILIKE %s "
            "ORDER BY name LIMIT %s",
            (f"%{query}%", f"%{query}%", limit),
        )
        return [self._row_to_symbol(r) for r in self.cur.fetchall()]

    # ── Explanation cache ─────────────────────────────────────────────────────

    def fetch_explanation(self, symbol_id: str) -> str | None:
        """Return the cached LLM explanation for a symbol, or None."""
        self.cur.execute(
            "SELECT text FROM explanations WHERE id = %s", (symbol_id,)
        )
        row = self.cur.fetchone()
        return row[0] if row else None

    def save_explanation(self, symbol_id: str, text: str) -> None:
        """Insert or replace the cached explanation for a symbol."""
        self.cur.execute(
            "INSERT INTO explanations (id, text) VALUES (%s, %s) "
            "ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text, generated_at = now()",
            (symbol_id, text),
        )

