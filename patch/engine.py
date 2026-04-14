import json
from pathlib import Path
from llm.client import LLMClient
from ingestion.database import DatabaseManager
from recommend.engine import RecommendationEngine
from .models import PatchResult
from .prompts import build_patch_system_prompt, build_patch_user_prompt
from .diffing import generate_unified_diff, parse_hunks, map_explanations_to_hunks, format_explained_diff

class PatchEngine:
    """Generates a code patch for a specific recommendation."""

    def __init__(
        self, 
        client: LLMClient, 
        db: DatabaseManager, 
        recommendation_engine: RecommendationEngine,
        patches_dir: Path = Path("data/patches")
    ):
        self.client = client
        self.db = db
        self.recommendation_engine = recommendation_engine
        self.patches_dir = patches_dir

    def generate(self, recommendation_id: str, force: bool = False) -> PatchResult:
        """Generate a patch for the given recommendation ID."""
        cache_file = self.patches_dir / f"{recommendation_id}.json"
        if not force and cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # We could reconstruct the PatchResult object here if needed
                # for now let's just re-generate or return as dict
                # To be consistent with the design, we'll return a PatchResult
                from .models import PatchHunkExplanation
                return PatchResult(
                    recommendation_id=data["recommendation_id"],
                    diff_text=data["diff_text"],
                    explained_diff_text=data["explained_diff_text"],
                    hunks=[PatchHunkExplanation(**h) for h in data["hunks"]],
                    files=data["files"]
                )

        # 1. Load recommendation
        recommendations = self.recommendation_engine.load()
        recommendation = next((r for r in recommendations if r.id == recommendation_id), None)
        if not recommendation:
            raise ValueError(f"Recommendation not found: {recommendation_id}")

        # 2. Gather file content
        repo_info = self.db.fetch_repo_info()
        repo_root = Path(repo_info["root"]) if repo_info else Path(".")
        
        files_content = {}
        for file_path in recommendation.files:
            abs_path = repo_root / file_path
            if abs_path.exists():
                files_content[file_path] = abs_path.read_text(encoding="utf-8")
            else:
                # Fallback to DB symbols if file not on disk? 
                # (User request said prefer reading from disk)
                # But for now let's just skip or error
                pass

        if not files_content:
            # Try primary file if files was empty
            abs_path = repo_root / recommendation.file
            if abs_path.exists():
                files_content[recommendation.file] = abs_path.read_text(encoding="utf-8")

        # 3. Build prompt and call LLM
        system_prompt = build_patch_system_prompt()
        user_prompt = build_patch_user_prompt(recommendation.to_dict(), files_content)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        raw_response = self.client.chat(messages, stream=False)
        
        # 4. Parse response
        try:
            patch_data = json.loads(raw_response)
        except json.JSONDecodeError:
            # Try to strip markdown
            if "```json" in raw_response:
                raw_response = raw_response.split("```json")[1].split("```")[0].strip()
                patch_data = json.loads(raw_response)
            else:
                raise

        # 5. Generate diffs and map explanations
        all_diff_texts = []
        all_hunk_explanations = []
        
        for file_patch in patch_data["files"]:
            path = file_patch["path"]
            new_content = file_patch["updated_content"]
            old_content = files_content.get(path, "")
            
            diff_text = generate_unified_diff(old_content, new_content, path)
            hunks_raw = parse_hunks(diff_text)
            
            # Filter explanations for this file
            file_explanations = [e for e in patch_data["explanations"] if e["path"] == path]
            hunk_explanations = map_explanations_to_hunks(hunks_raw, file_explanations)
            
            all_diff_texts.append(diff_text)
            all_hunk_explanations.extend(hunk_explanations)

        combined_diff = "\n".join(all_diff_texts)
        explained_diff = format_explained_diff(combined_diff, all_hunk_explanations)

        result = PatchResult(
            recommendation_id=recommendation_id,
            diff_text=combined_diff,
            explained_diff_text=explained_diff,
            hunks=all_hunk_explanations,
            files=list(files_content.keys())
        )

        # 6. Cache result
        self.patches_dir.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

        return result
