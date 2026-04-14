import json
from pathlib import Path
from .models import Recommendation

def validate_recommendations(raw_json: str, ingested_files: set[str]) -> list[Recommendation]:
    """Parse JSON, validate required keys, and filter by existing files."""
    def _try_parse(text: str) -> any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Salvage attempt: Find the last complete object '}' and close the array ']'
            last_brace = text.rfind('}')
            if last_brace != -1:
                salvaged = text[:last_brace + 1] + "\n]"
                try:
                    return json.loads(salvaged)
                except json.JSONDecodeError:
                    pass
            return None

    # Step 1: Try raw parsing
    data = _try_parse(raw_json)

    # Step 2: Try stripping Markdown if raw failed
    if data is None and "```json" in raw_json:
        stripped = raw_json.split("```json")[1].split("```")[0].strip()
        data = _try_parse(stripped)

    # Step 3: Failure handling
    if data is None:
        raise ValueError(
            "The LLM response was truncated or invalid JSON. "
            "Please increase the 'max_tokens' setting in your config.toml "
            "to allow for longer responses."
        )

    if not isinstance(data, list):
        raise ValueError("Root must be a list")

    results = []
    seen_ids = set()
    
    for item in data:
        # Basic key validation
        required = ["id", "title", "level", "description", "file"]
        if not all(k in item for k in required):
            continue
            
        if item["id"] in seen_ids:
            continue
            
        # Verify primary file exists in the repo
        if item["file"] not in ingested_files:
            continue
            
        # Clean up related files
        if "files" in item:
            item["files"] = [f for f in item["files"] if f in ingested_files]
        else:
            item["files"] = [item["file"]]
            
        if item["file"] not in item["files"]:
            item["files"].append(item["file"])
            
        rec = Recommendation.from_dict(item)
        results.append(rec)
        seen_ids.add(rec.id)
        
    return results
