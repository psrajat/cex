import json
from pathlib import Path
from llm.client import LLMClient
from ingestion.database import DatabaseManager
from recommend.engine import RecommendationEngine
from .models import PatchResult
from .prompts import build_patch_system_prompt, build_patch_user_prompt
from .diffing import generate_unified_diff, parse_hunks, map_explanations_to_hunks, format_explained_diff
from llm.logger import log_prompt

class PatchEngine:
    """Generates a code patch for a specific recommendation."""

    def __init__(
        self, 
        client: LLMClient, 
        db: DatabaseManager, 
        recommendation_engine: RecommendationEngine,
        log_cfg = None
    ):
        self.client = client
        self.db = db
        self.recommendation_engine = recommendation_engine
        self.log_cfg = log_cfg

    def generate(self, recommendation_id: str, force: bool = False) -> PatchResult:
        """Generate a patch for the given recommendation ID."""
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

        if self.log_cfg:
            log_prompt(messages, recommendation_id, self.log_cfg, log_name="patches.log")

        print(f"Generating patch for: {recommendation_id}")
        raw_response = self.client.chat(messages, stream=False)
        
        # Log raw response
        if self.log_cfg:
            from datetime import datetime
            log_dir = Path(self.log_cfg.log_dir) / "patches"
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(log_dir / f"response_{recommendation_id}_{ts}.json", "w") as f:
                f.write(raw_response)
        
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
        file_patches = []
        
        for file_patch in patch_data["files"]:
            path = file_patch["path"]
            new_content = file_patch["updated_content"]
            old_content = files_content.get(path, "")
            
            file_patches.append({
                "path": path,
                "old": old_content,
                "new": new_content
            })
            
            diff_text = generate_unified_diff(old_content, new_content, path)
            hunks_raw = parse_hunks(diff_text)
            
            # Filter explanations for this file
            file_explanations = [e for e in patch_data.get("explanations", []) if e.get("path") == path]
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
            files=list(files_content.keys()),
            file_patches=file_patches
        )

        print(f"Patch generated successfully ({len(file_patches)} files).")
        return result
