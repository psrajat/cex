from pathlib import Path
import textwrap
from ingestion.database import DatabaseManager

class SkeletonEngine:
    """Generates a compact, LLM-friendly architectural summary of the ingested repo."""

    def __init__(self, db: DatabaseManager, output_path: Path = Path("data/skeleton.md")):
        self.db = db
        self.output_path = output_path

    def build(self, force: bool = False) -> Path:
        """Fetch indexed data and write the markdown skeleton to disk."""
        if not force and self.output_path.exists():
            return self.output_path

        repo_info = self.db.fetch_repo_info()
        if not repo_info:
            raise ValueError("No repository ingested yet. Run 'cex ingest' first.")

        deps = self.db.fetch_all_dependencies()
        all_symbols = self.db.fetch_all_symbols()

        # Group symbols by file
        file_symbols = {}
        for sym in all_symbols:
            if sym.file_path not in file_symbols:
                file_symbols[sym.file_path] = []
            file_symbols[sym.file_path].append(sym)

        lines = [
            "# Repository Skeleton\n",
            "## Repo",
            f"- root: {repo_info['root']}",
            f"- language: {repo_info['language']}\n",
        ]

        if deps:
            lines.append("## Dependencies")
            for d in deps:
                version = f" ({d.version})" if d.version else ""
                lines.append(f"- {d.name}{version}")
            lines.append("")

        lines.append("## Files")
        
        # Sort files by path for stability
        for file_path in sorted(file_symbols.keys()):
            lines.append(f"\n### {file_path}")
            
            # Fetch imports for this file
            self.db.cur.execute(
                "SELECT module, names FROM file_imports WHERE file_id = %s",
                (file_path,)
            )
            imports = self.db.cur.fetchall()
            if imports:
                import_strs = []
                for mod, names in imports:
                    if names:
                        import_strs.append(f"{mod}({', '.join(names)})")
                    else:
                        import_strs.append(mod)
                lines.append(f"Imports: {', '.join(import_strs)}")

            lines.append("Top-level symbols:")
            for sym in file_symbols[file_path]:
                # Deterministic skeleton line
                # We also include caller/callee counts for architectural signal
                callers = self.db.fetch_related_symbols(sym.qualified_name, "CALLS", direction="in")
                callees = self.db.fetch_related_symbols(sym.qualified_name, "CALLS", direction="out")
                
                sig = sym.signature.strip() if sym.signature else sym.name
                lines.append(f"- {sig} [{sym.type}] lines {sym.start_line}-{sym.end_line}")
                lines.append(f"  parent: {sym.qualified_name.rsplit('.', 1)[0] if '.' in sym.qualified_name else 'none'}")
                lines.append(f"  callers: {len(callers)}  callees: {len(callees)}")
                
                # Check if it's an "important" symbol to include a short sketch
                # We consider 'endpoint', 'model', or symbols with many callers/callees as important
                if sym.type in ('endpoint', 'model') or len(callers) + len(callees) > 5:
                   # Extract docstring or first few lines of body
                   # Very simple heuristic: first 3 lines of body
                   body_lines = sym.code_body.splitlines()
                   sketch = []
                   for bl in body_lines:
                       bl_stripped = bl.strip()
                       if not bl_stripped or bl_stripped.startswith(('def ', 'class ', '@')):
                           continue
                       sketch.append(bl_stripped)
                       if len(sketch) >= 2:
                           break
                   if sketch:
                       summary = " ".join(sketch)[:100]
                       lines.append(f"  role: {summary}...")

        output_dir = self.output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.output_path.write_text("\n".join(lines), encoding="utf-8")
        return self.output_path

    def load(self) -> str:
        """Return the content of the skeleton file."""
        if not self.output_path.exists():
            self.build()
        return self.output_path.read_text(encoding="utf-8")
