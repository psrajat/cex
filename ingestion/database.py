import json
import psycopg2
from psycopg2 import extras
from .models import DependencyModel, FileModel


class DatabaseManager:
    """Thin wrapper around a psycopg2 connection for cex database operations.

    All primary keys are human-readable TEXT derived from natural keys:
      files.id        = relative file path   ('schedule/__init__.py')
      symbols.id      = qualified_name        ('schedule.__init__.Scheduler')
      relations.id    = '{src}::{type}::{tgt}'
      dependencies.id = '{manifest_file}::{name}'
      file_imports.id = '{file_id}::{module}'
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

    # ── Batch inserts ─────────────────────────────────────────────────────────

    def batch_insert_symbols(self, symbols: list[tuple]) -> None:
        """symbols: list of
        (id, file_id, type, name, qualified_name, signature, code_body,
         start_line, end_line, metadata_json_str) tuples.
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
        """relations: list of (id, source_symbol_id, target_symbol_id, relation_type) tuples."""
        if not relations:
            return
        extras.execute_values(
            self.cur,
            "INSERT INTO relations (id, source_symbol_id, target_symbol_id, relation_type)"
            " VALUES %s ON CONFLICT (id) DO NOTHING",
            relations,
        )

    def insert_file_imports(self, file_id: str, imports: list[tuple[str, list[str]]]) -> None:
        """imports: list of (module_name, [imported_names]) tuples from parse_symbols_and_relations."""
        if not imports:
            return
        # psycopg2 converts Python lists to TEXT[] automatically.
        extras.execute_values(
            self.cur,
            "INSERT INTO file_imports (id, file_id, module, names) VALUES %s ON CONFLICT (id) DO NOTHING",
            [(f"{file_id}::{module}", file_id, module, names) for module, names in imports],
        )
