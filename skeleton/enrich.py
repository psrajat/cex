import re
import os
from typing import List, Dict, Any, Optional
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

        # 1. Repo Summary
        repo_map.summary = self._generate_summary()

        # 2. Main Subsystems
        repo_map.subsystems = self._generate_subsystems()

        # 3. Rank and Enrich Files
        ranked_files = self._rank_files()
        for f_data in ranked_files[:self.config.max_files]:
            file_path = f_data['path']
            enriched_file = EnrichedFile(
                path=file_path,
                role=self._infer_role(file_path),
                why_it_matters=self._infer_why_it_matters(file_path),
                score=f_data['score'],
                explanation=self._get_explanation(file_path)
            )

            # 4. Rank and Enrich Symbols for this file
            enriched_file.symbols = self._get_ranked_symbols(file_path)
            repo_map.important_files.append(enriched_file)

        # 5. Suggested Reading Paths
        repo_map.reading_paths = self._generate_reading_paths()

        # 6. Gaps / Limitations
        repo_map.gaps = self._generate_gaps()

        return repo_map

    def _generate_summary(self) -> Dict[str, str]:
        repo_info = self.db.fetch_repo_info()
        return {
            "Purpose": repo_info.get("metadata", {}).get("purpose", "Code analysis and explanation tool."),
            "Primary language": repo_info.get("language", "Python"),
            "Main entrypoints": "main.py, api/server.py",
            "Core capabilities": "ingestion, embedding, search, explanation, API serving"
        }

    def _generate_subsystems(self) -> List[Subsystem]:
        """Inferred from top-level directories."""
        subsystems = []
        # Get top-level dirs from files table
        self.db.cur.execute("SELECT DISTINCT split_part(id, '/', 1) FROM files WHERE id LIKE '%%/%%'")
        dirs = [r[0] for r in self.db.cur.fetchall() if r[0]]
        
        descriptions = {
            "ingestion": "Parses repository files and stores extracted structure",
            "search": "Performs semantic and keyword retrieval",
            "explain": "Generates and caches explanations",
            "api": "Serves endpoints for files, search, and explanation",
            "llm": "Wraps the OpenAI-compatible backend",
            "ui": "Frontend for exploration and explanation"
        }

        for d in dirs:
            desc = descriptions.get(d, self._get_explanation(d) or "Supporting subsystem logic.")
            subsystems.append(Subsystem(name=d, description=desc))
        
        return subsystems

    def _rank_files(self) -> List[Dict[str, Any]]:
        """
        file_score = 4 * explanation_exists + 3 * symbol_count + 2 * import_count + 3 * path_bonus + 2 * filename_bonus
        """
        self.db.cur.execute("""
            SELECT f.id, 
                   COUNT(DISTINCT s.id) as sym_count,
                   (SELECT COUNT(*) FROM file_imports WHERE file_id = f.id) as imp_count,
                   EXISTS(SELECT 1 FROM explanations WHERE id = f.id) as has_exp
            FROM files f
            LEFT JOIN symbols s ON s.file_id = f.id
            GROUP BY f.id
        """)
        files_data = self.db.cur.fetchall()

        ranked = []
        for fid, sym_count, imp_count, has_exp in files_data:
            score = (4 if has_exp else 0) + (3 * sym_count) + (2 * imp_count)
            
            # path_role_bonus
            if any(p in fid for p in ['api/', 'engine.py', 'client.py', 'parser.py', 'main.py', 'config', 'setup']):
                score += 3
            
            # filename_bonus
            fname = os.path.basename(fid)
            if fname in ['main.py', 'server.py', 'engine.py', 'client.py', 'parser.py', 'setup_db.py']:
                score += 2
            
            ranked.append({'path': fid, 'score': float(score)})
        
        return sorted(ranked, key=lambda x: x['score'], reverse=True)

    def _get_ranked_symbols(self, file_path: str) -> List[EnrichedSymbol]:
        """
        symbol_score = 4 * explanation_exists + 3 * public_bonus + 3 * type_bonus + 2 * signature_exists
        """
        self.db.cur.execute("""
            SELECT s.qualified_name, s.name, s.type, s.signature,
                   EXISTS(SELECT 1 FROM explanations WHERE id = s.qualified_name) as has_exp
            FROM symbols s
            WHERE s.file_id = %s
        """, (file_path,))
        symbols = self.db.cur.fetchall()

        ranked = []
        for qname, name, stype, sig, has_exp in symbols:
            score = (4 if has_exp else 0)
            
            if not name.startswith('_'):
                score += 3
            
            if stype in ['class', 'endpoint']:
                score += 3
            elif stype == 'function':
                score += 2
            
            if sig:
                score += 2
            
            ranked.append(EnrichedSymbol(
                name=name,
                type=stype,
                signature=sig or "",
                explanation=self._get_explanation(qname),
                score=float(score)
            ))
        
        return sorted(ranked, key=lambda x: x['score'], reverse=True)[:self.config.max_symbols_per_file]

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

    def _generate_reading_paths(self) -> List[str]:
        return [
            "To understand API flow: api/server.py -> explain/engine.py -> llm/client.py",
            "To understand indexing: main.py -> ingestion/engine.py -> ingestion/parser.py",
            "To understand retrieval: search/retriever.py -> search/embeddings.py"
        ]

    def _generate_gaps(self) -> List[str]:
        return [
            "Repo map is partial and ranked based on symbols and explanations.",
            "Parsing is primarily Python-focused.",
            "Cached explanations may lag behind recent source changes."
        ]
