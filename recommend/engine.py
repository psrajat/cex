import json
import threading
from pathlib import Path
from llm.client import LLMClient
from skeleton.engine import SkeletonEngine
from .models import Recommendation
from .prompts import build_recommendation_system_prompt, build_recommendation_user_prompt
from .validator import validate_recommendations
from llm.logger import log_prompt

class RecommendationEngine:
    """Generates actionable PR ideas from the skeleton and stores them as JSON."""

    def __init__(
        self, 
        client: LLMClient, 
        skeleton_engine: SkeletonEngine, 
        log_cfg = None
    ):
        self.client = client
        self.skeleton_engine = skeleton_engine
        self.log_cfg = log_cfg
        self._cached_recs: list[Recommendation] | None = None
        self._lock = threading.Lock()

    def generate(self, force: bool = False) -> list[Recommendation]:
        """Ask the LLM for recommendations based on the skeleton."""
        with self._lock:
            if not force and self._cached_recs is not None:
                return self._cached_recs
        
            print(f"Generating recommendations for project...")
            skeleton_text = self.skeleton_engine.load()
            repo_info = self.skeleton_engine.db.fetch_repo_info()
            repo_root = repo_info["root"] if repo_info else "current-repo"
            repo_name = Path(repo_root).name

            system_prompt = build_recommendation_system_prompt()
            user_prompt = build_recommendation_user_prompt(repo_name, skeleton_text)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            if self.log_cfg:
                log_prompt(messages, repo_name, self.log_cfg, log_name="recommendations.log")

            raw_response = self.client.chat(messages)
            
            # Get set of all files in the DB to validate recommendations
            files_rows = self.skeleton_engine.db.fetch_all_symbols()
            ingested_files = {s.file_path for s in files_rows}
            
            recommendations = validate_recommendations(raw_response, ingested_files)
            self._cached_recs = recommendations
            
            # Log a snapshot with timestamp
            if self.log_cfg:
                from datetime import datetime
                log_dir = Path(self.log_cfg.log_dir) / "recommendations"
                log_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_file = log_dir / f"recs_{ts}.json"
                with open(log_file, "w", encoding="utf-8") as f:
                    json.dump([r.to_dict() for r in recommendations], f, indent=2)

            # Persistence: avoid re-generation across server restarts by project
            try:
                cache_file = Path("data") / f"{self.skeleton_engine.db.config.name}_recs.json"
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump([r.to_dict() for r in recommendations], f, indent=2)
            except Exception as e:
                print(f"Warning: could not cache recommendations: {e}")
            
            print(f"Recommendations generated: {len(recommendations)} items.")
            return recommendations

    def load(self) -> list[Recommendation]:
        """Return memory-cached recommendations, load from file, or generate them."""
        if self._cached_recs is not None:
            return self._cached_recs
            
        try:
            cache_file = Path("data") / f"{self.skeleton_engine.db.config.name}_recs.json"
            if cache_file.exists():
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._cached_recs = [Recommendation.from_dict(d) for d in data]
                    return self._cached_recs
        except Exception as e:
            print(f"Warning: could not load recommendation cache: {e}")

        return self.generate()
