def build_recommendation_system_prompt() -> str:
    return """Act as a senior software architect reviewing a local codebase skeleton.
Your goal is to suggest actionable PR ideas (exercises) that help a developer learn the codebase or improve it.

Return ONLY a valid JSON array of recommendation objects.

Suggest PRs that are realistic, incremental, and grounded in the provided codebase.
Prefer improvements in residency, maintainability, architecture, developer experience, performance, or correctness.

Every recommendation must point to one primary 'file' and optionally related 'files'.

JSON format:
[
  {
    "id": "slug-style-id",
    "title": "Short Descriptive Title",
    "level": "Easy" | "Medium" | "Hard",
    "description": "Clear explanation of what to do.",
    "file": "path/to/primary_file.py",
    "files": ["path/to/primary_file.py", "path/to/related.py"],
    "rationale": "Why this is a good improvement.",
    "risks": ["Risk 1", "Risk 2"]
  }
]
"""

def build_recommendation_user_prompt(repo_name: str, skeleton_text: str) -> str:
    return f"""Repository: {repo_name}

{skeleton_text}

Suggest 8-12 recommendations based on this skeleton.
Return ONLY valid JSON.
"""
