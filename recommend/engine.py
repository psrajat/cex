import json
from pathlib import Path
from llm.client import LLMClient
from skeleton.engine import SkeletonEngine
from .models import Recommendation
from .prompts import build_recommendation_system_prompt, build_recommendation_user_prompt
from .validator import validate_recommendations

class RecommendationEngine:
    """Generates actionable PR ideas from the skeleton and stores them as JSON."""

    def __init__(
        self, 
        client: LLMClient, 
        skeleton_engine: SkeletonEngine, 
        output_path: Path = Path("data/recommendations.json")
    ):
        self.client = client
        self.skeleton_engine = skeleton_engine
        self.output_path = output_path

    def generate(self, force: bool = False) -> list[Recommendation]:
        """Ask the LLM for recommendations based on the skeleton and save to disk."""
        if not force and self.output_path.exists():
            return self.load()

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

        # Use chat completion (client.chat_completion or similar)
        # Looking at LLMClient in previous turns, it has stream_chat and chat.
        # Let's check LLMClient exactly.
        raw_response = self.client.chat(messages)
        
        # Get set of all files in the DB to validate recommendations
        files_rows = self.skeleton_engine.db.fetch_all_symbols()
        ingested_files = {s.file_path for s in files_rows}
        
        recommendations = validate_recommendations(raw_response, ingested_files)
        
        # Save to disk
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in recommendations], f, indent=2)
            
        return recommendations

    def load(self) -> list[Recommendation]:
        """Load recommendations from the JSON file."""
        if not self.output_path.exists():
            return self.generate()
        
        with open(self.output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [Recommendation.from_dict(d) for d in data]
