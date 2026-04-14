from pathlib import Path
from ingestion.database import DatabaseManager
from .models import RepoMapConfig
from .enrich import RepoMapEnricher
from .writer import RepoMapWriter

class SkeletonEngine:
    """Generates a ranked, explanation-enriched repository map index."""

    def __init__(self, db: DatabaseManager, output_path: Path = Path("data/repo_map.md")):
        self.db = db
        self.config = RepoMapConfig(final_output_path=output_path)
        
        # Components
        self.enricher = RepoMapEnricher(self.db, self.config)
        self.writer = RepoMapWriter()

    def build(self, force: bool = False) -> Path:
        """Fetch indexed data and write the repository map to disk."""
        # 1. Generate the map from DB
        repo_map_data = self.enricher.build_map()
        
        # 2. Write to markdown
        return self.writer.write(repo_map_data, self.config.final_output_path)

    def load(self) -> str:
        """Return the content of the repo map file."""
        if not self.config.final_output_path.exists():
            self.build()
        return self.config.final_output_path.read_text(encoding="utf-8")
