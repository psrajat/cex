import json
from pathlib import Path
from .models import Recommendation

def validate_recommendations(raw_json: str, ingested_files: set[str]) -> list[Recommendation]:
    """Parse JSON, validate required keys, and filter by existing files."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        # If it's wrapped in markdown code blocks, try to strip them
        if "```json" in raw_json:
            raw_json = raw_json.split("```json")[1].split("```")[0].strip()
            data = json.loads(raw_json)
        else:
            raise

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
