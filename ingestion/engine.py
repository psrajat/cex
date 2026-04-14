"""ingestion/engine.py

Orchestrates the full ingestion pipeline for a single repository:
  1. Dependencies — scans manifest files (requirements.txt, pyproject.toml)
  2. Files       — discovers and records all source files
  3. Symbols     — tree-sitter AST parse per file: symbols, relations, imports

All DB operations use idempotent ON CONFLICT DO NOTHING statements, so
re-ingesting a repository is safe (it adds new data, never overwrites).
"""

import json
from pathlib import Path

from .parser import CodeParser
from .database import DatabaseManager


class IngestionEngine:
    """Coordinates parsing and persistence for one repository directory.

    Typical usage::

        engine = IngestionEngine("/path/to/repo", db_config)
        engine.run()
    """

    def __init__(self, repo_dir: str, db_config, on_progress=None):
        self.repo_dir = Path(repo_dir).resolve()
        self.parser = CodeParser(self.repo_dir)
        self.db = DatabaseManager(db_config)
        self.on_progress = on_progress

    def _log(self, msg: str) -> None:
        if self.on_progress:
            self.on_progress(msg)
        else:
            print(msg)

    def run(self) -> None:
        """Run the full pipeline: connect → ingest → close."""
        self.db.connect()
        try:
            # Record the repository root so LLM context can reference it.
            self.db.upsert_repo_info(str(self.repo_dir), "python")
            self._ingest_dependencies()
            self._ingest_files()
        finally:
            self.db.close()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _ingest_dependencies(self) -> None:
        """Parse manifest files and store package dependency records."""
        deps = self.parser.parse_manifests()
        self.db.insert_dependencies(deps)

    def _ingest_files(self) -> None:
        """Discover source files, parse each one, and persist all artefacts."""
        files = self.parser.parse_files()
        if not files:
            self._log("No source files found.")
            return
        self.db.insert_files(files)

        total_symbols = total_relations = total_imports = 0

        self._log(f"Scanning {len(files)} files…")
        for i, file_model in enumerate(files, 1):
            file_path = self.repo_dir / file_model.path

            # A single tree walk produces symbols, structural/call relations,
            # and module import statements for this file.
            symbols, relations, imports = self.parser.parse_symbols_and_relations(file_path)

            # TEXT PKs are derived from natural keys — no DB round-trips needed.
            file_id = file_model.path

            self.db.batch_insert_symbols([
                (
                    s.qualified_name, file_id, s.type, s.name, s.qualified_name,
                    s.signature, s.code_body,
                    s.start_line, s.end_line,
                    json.dumps(s.metadata),
                )
                for s in symbols
            ])

            self.db.insert_file_imports(file_id, imports)

            # Relation id = '{source_qname}::{rel_type}::{target_qname}'
            self.db.batch_insert_relations([
                (f"{r.source_qname}::{r.relation_type}::{r.target_qname}",
                 r.source_qname, r.target_qname, r.relation_type)
                for r in relations
            ])

            total_symbols += len(symbols)
            total_relations += len(relations)
            total_imports += len(imports)
            self._log(f"[{i}/{len(files)}] {file_model.path}: {len(symbols)} symbols, {len(relations)} relations")

        self._log(
            f"\nIngestion complete: {len(files)} files | "
            f"{total_symbols} symbols | {total_relations} relations | "
            f"{total_imports} imports"
        )

