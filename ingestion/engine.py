import json
from pathlib import Path

from .parser import CodeParser
from .database import DatabaseManager


class IngestionEngine:
    def __init__(self, repo_dir: str, db_config):
        self.repo_dir = Path(repo_dir).resolve()
        self.parser = CodeParser(self.repo_dir)
        self.db = DatabaseManager(db_config)

    def run(self) -> None:
        self.db.connect()
        try:
            self.db.upsert_repo_info(str(self.repo_dir), "python")
            self._ingest_dependencies()
            self._ingest_files()
        finally:
            self.db.close()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _ingest_dependencies(self) -> None:
        deps = self.parser.parse_manifests()
        self.db.insert_dependencies(deps)

    def _ingest_files(self) -> None:
        files = self.parser.parse_files()
        if not files:
            print("No source files found.")
            return
        self.db.insert_files(files)

        total_symbols = total_relations = total_imports = 0

        for file_model in files:
            file_path = self.repo_dir / file_model.path
            # Single tree walk: symbols + NESTED_IN/CALLS relations + import statements.
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
            print(f"  {file_model.path}: {len(symbols)} symbols, {len(relations)} relations")

        print(
            f"\nIngestion complete: {len(files)} files | "
            f"{total_symbols} symbols | {total_relations} relations | "
            f"{total_imports} imports"
        )
