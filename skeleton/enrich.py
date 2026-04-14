import re
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from .models import RepoMap, EnrichedFile, EnrichedSymbol, Subsystem, RepoMapConfig
from ingestion.database import DatabaseManager

class RepoMapEnricher:
    """Generates a ranked, explanation-enriched repository map index."""

    def __init__(self, db: DatabaseManager, config: RepoMapConfig):
        self.db = db
        self.config = config

    def build_map(self) -> RepoMap:
        """Main entry point for generating the repo map."""
        if not self.db.cur:
            self.db.connect()

        repo_map = RepoMap()

        # 3. Rank and Enrich Files
        ranked_files = self._rank_files()
        enriched_files = []
        for f_data in ranked_files[:self.config.max_files]:
            file_path = f_data['path']
            file_exp = self._get_explanation(file_path)
            symbols = self._get_ranked_symbols(file_path)
            role, why_it_matters = self._derive_role_and_why(file_path, file_exp, symbols)

            enriched_file = EnrichedFile(
                path=file_path,
                role=role,
                why_it_matters=why_it_matters,
                score=f_data['score'],
                explanation=file_exp,
                symbols=symbols
            )
            enriched_files.append(enriched_file)
            
        repo_map.important_files = enriched_files

        # 1. Repo Summary
        repo_map.summary = self._generate_summary(enriched_files)

        # 2. Main Subsystems
        repo_map.subsystems = self._generate_subsystems(enriched_files)

        # 5. Suggested Reading Paths
        repo_map.reading_paths = self._generate_reading_paths(enriched_files)

        # 6. Gaps / Limitations
        repo_map.gaps = self._generate_gaps(ranked_files, enriched_files)

        return repo_map

    def _derive_role_and_why(self, path: str, file_exp: Optional[str], symbols: List[EnrichedSymbol]) -> Tuple[str, str]:
        if file_exp:
            sentences = re.split(r'(?<=[.!?])\s+', file_exp.strip())
            role = sentences[0] if sentences else file_exp
            why = " ".join(sentences[1:]) if len(sentences) > 1 else self._infer_why_it_matters(path)
            return role.strip(), why.strip()

        sym_exps = [s.explanation for s in symbols if s.explanation]
        if sym_exps:
            role = sym_exps[0]
            why = " ".join(sym_exps[1:3]) if len(sym_exps) > 1 else self._infer_why_it_matters(path)
            return role.strip(), why.strip()
            
        if symbols:
            role = f"Defines {symbols[0].type} {symbols[0].name}"
            why = f"Contains {len(symbols)} key symbols including " + ", ".join(s.name for s in symbols[:3])
            return role.strip(), why.strip()

        return self._infer_role(path), self._infer_why_it_matters(path)

    def _generate_summary(self, enriched_files: List[EnrichedFile]) -> Dict[str, str]:
        repo_info = self.db.fetch_repo_info()
        entrypoints = [f.path for f in enriched_files if f.path.endswith('main.py') or f.path.endswith('server.py') or 'setup' in f.path or 'bootstrap' in f.path]
        if not entrypoints:
            entrypoints = [f.path for f in enriched_files[:3]]

        dirs = set(f.path.split('/')[0] for f in enriched_files if '/' in f.path)
        caps = list(dirs) if dirs else ["components"]
        
        return {
            "Purpose": repo_info.get("metadata", {}).get("purpose", "Code analysis and explanation tool."),
            "Primary language": repo_info.get("language", "Python"),
            "Main entrypoints": ", ".join(entrypoints[:3]) if entrypoints else "Inferred from files",
            "Core capabilities": ", ".join(caps[:5])
        }

    def _generate_subsystems(self, enriched_files: List[EnrichedFile]) -> List[Subsystem]:
        """Inferred from top-level directories and actual evidence."""
        subsystems = []
        dir_to_files = {}
        for f in enriched_files:
            if '/' in f.path:
                d = f.path.split('/')[0]
                dir_to_files.setdefault(d, []).append(f)
                
        for d, files in dir_to_files.items():
            exps = []
            for f in files:
                if f.explanation:
                    exps.append(f.explanation)
                for s in f.symbols:
                    if s.explanation:
                        exps.append(s.explanation)
            
            desc = exps[0] if exps else f"Contains {len(files)} key files."
            subsystems.append(Subsystem(name=d, description=desc))
        
        return subsystems

    def _rank_files(self) -> List[Dict[str, Any]]:
        self.db.cur.execute("""
            SELECT f.id, 
                   COUNT(DISTINCT s.id) as sym_count,
                   EXISTS(SELECT 1 FROM explanations WHERE id = f.id) as has_exp,
                   (SELECT COUNT(*) FROM symbols s2 JOIN explanations e ON s2.qualified_name = e.id WHERE s2.file_id = f.id) as exp_sym_count
            FROM files f
            LEFT JOIN symbols s ON s.file_id = f.id
            GROUP BY f.id
        """)
        files_data = self.db.cur.fetchall()

        ranked = []
        for fid, sym_count, has_exp, exp_sym_count in files_data:
            score = 0.0
            if has_exp:
                score += 10.0
            score += (exp_sym_count * 2.0)
            
            fid_lower = fid.lower()
            if any(p in fid_lower for p in ['api', 'client', 'server', 'router', 'endpoint']):
                score += 5.0
            if any(p in fid_lower for p in ['main.py', 'setup', 'bootstrap', 'app.py', 'core', 'engine']):
                score += 5.0
                
            if sym_count > 0:
                score += min(sym_count, 10) * 0.1
                
            ranked.append({'path': fid, 'score': score})
        
        return sorted(ranked, key=lambda x: x['score'], reverse=True)

    def _get_ranked_symbols(self, file_path: str) -> List[EnrichedSymbol]:
        self.db.cur.execute("""
            SELECT s.qualified_name, s.name, s.type, s.signature,
                   EXISTS(SELECT 1 FROM explanations WHERE id = s.qualified_name) as has_exp
            FROM symbols s
            WHERE s.file_id = %s
        """, (file_path,))
        symbols = self.db.cur.fetchall()

        ranked = []
        for qname, name, stype, sig, has_exp in symbols:
            score = 0.0
            if has_exp:
                score += 10.0
            if not name.startswith('_'):
                score += 5.0
            if sig:
                score += 2.0
            if stype in ['class', 'endpoint', 'interface']:
                score += 4.0
            elif stype == 'method' and not name.startswith('_'):
                score += 2.0
            elif stype == 'function':
                score += 1.0
            
            ranked.append(EnrichedSymbol(
                name=name,
                type=stype,
                signature=sig or "",
                explanation=self._get_explanation(qname),
                score=score
            ))
        
        return sorted(ranked, key=lambda x: x.score, reverse=True)[:self.config.max_symbols_per_file]

    def _get_explanation(self, target_id: str) -> Optional[str]:
        self.db.cur.execute("SELECT text FROM explanations WHERE id = %s", (target_id,))
        row = self.db.cur.fetchone()
        if row:
            text = row[0].replace('\n', ' ').strip()
            sentences = re.split(r'(?<=[.!?])\s+', text)
            summary = sentences[0] if sentences else text
            return summary[:160]
        return None

    def _infer_role(self, path: str) -> str:
        if 'api/' in path: return "API bootstrap and route layer"
        if 'engine.py' in path: return "Core logic orchestration"
        if 'main.py' in path: return "CLI entrypoint"
        if 'parser.py' in path: return "Stateless code parser"
        return "Internal logic module"

    def _infer_why_it_matters(self, path: str) -> str:
        if 'server.py' in path: return "Creates shared services and exposes HTTP endpoints."
        if 'explain/' in path: return "Resolves targets and coordinates LLM prompting."
        if 'db' in path or 'models' in path: return "Defines the data contracts and persistence schema."
        return "Provides necessary utilities and business logic."

    def _generate_reading_paths(self, enriched_files: List[EnrichedFile]) -> List[str]:
        paths = []
        api_files = [f.path for f in enriched_files if 'api' in f.path or 'server' in f.path]
        engine_files = [f.path for f in enriched_files if 'engine' in f.path or 'core' in f.path]
        backend_files = [f.path for f in enriched_files if 'client' in f.path or 'db' in f.path]
        
        if api_files and engine_files and backend_files:
            paths.append(f"API Flow: {api_files[0]} -> {engine_files[0]} -> {backend_files[0]}")
            
        entry_files = [f.path for f in enriched_files if 'main' in f.path or 'setup' in f.path]
        ingest_files = [f.path for f in enriched_files if 'ingest' in f.path]
        parse_files = [f.path for f in enriched_files if 'parse' in f.path or 'index' in f.path]
        
        if entry_files and ingest_files and parse_files:
            paths.append(f"Indexing path: {entry_files[0]} -> {ingest_files[0]} -> {parse_files[0]}")
            
        retrieval_files = [f.path for f in enriched_files if 'search' in f.path or 'retrieve' in f.path]
        if retrieval_files:
            paths.append(f"Retrieval path: {' -> '.join(retrieval_files[:3])}")
            
        if not paths:
            paths = [f"General flow: {' -> '.join(f.path for f in enriched_files[:3])}"]
            
        return paths

    def _generate_gaps(self, ranked_files: List[Dict[str, Any]], enriched_files: List[EnrichedFile]) -> List[str]:
        gaps = []
        total_files = len(ranked_files)
        shown_files = len(enriched_files)
        if total_files > shown_files:
            gaps.append(f"Repo map partiality: Showing {shown_files} of {total_files} ranked files (based on configured max_files).")
            
        has_exps = any(f.explanation for f in enriched_files) or any(s.explanation for f in enriched_files for s in f.symbols)
        if has_exps:
            gaps.append("Explanations are cached and may not reflect uncommitted or very recent code changes.")
        else:
            gaps.append("Repo currently lacks generated explanations; relying on names and signatures.")
            
        gaps.append(f"Symbol details are limited to top {self.config.max_symbols_per_file} per file.")
        return gaps
