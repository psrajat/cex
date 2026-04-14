def build_recommendation_system_prompt() -> str:
    return """Act as a senior software architect reviewing a local codebase skeleton.
Your goal is to suggest actionable PR ideas (exercises) that help a developer learn the codebase or improve it.

Return ONLY a valid JSON array of recommendation objects.

You MUST generate exactly 9 recommendations: 3 Easy, 3 Medium, and 3 Hard.
CRITICAL: These recommendations must be grounded in the provided codebase. Focus on real-world refactoring, decoupling, architecture, state management, security, or domain-driven design tasks. Do NOT suggest superficial changes (e.g., adding type hints where obvious, or random docstrings) unless specifically addressing complex technical debt. Ensure that the difficulty level accurately reflects the real-world complexity of the change.

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

Provide exactly 9 high-quality, real-world recommendations (3 Easy, 3 Medium, 3 Hard) based directly on this skeleton. Do not use random placeholder ideas.
Return ONLY valid JSON.
"""
