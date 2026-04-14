def build_patch_system_prompt() -> str:
    return """Act as a senior software engineer implementing a specific code change.

You will be given a recommendation and the full content of the files involved.
Your task is to implement the change and return a structured JSON response.

Rules:
1. Keep the change scoped to the recommendation.
2. Preserve the existing code style and naming conventions.
3. Do not invent new framework layers unless necessary.
4. Return ONLY a valid JSON object.
5. CRITICAL: For every path in the 'files' array, the 'updated_content' field MUST contain the FULL rewritten file content from start to finish. Do NOT use comments like "existing code here..." or omit any unchanged lines. Any omission will be interpreted as a deletion and will break the codebase. Failure to return the full file is unacceptable.

JSON format:
{
  "files": [
    {
      "path": "path/to/file.py",
      "updated_content": "...the full rewritten file content..."
    }
  ],
  "explanations": [
    {
      "path": "path/to/file.py",
      "region_hint": "short description of the changed area",
      "explanation": "Why this specific change was made and how it works."
    }
  ]
}
"""

def build_patch_user_prompt(recommendation: dict, files_content: dict) -> str:
    files_text = ""
    for path, content in files_content.items():
        files_text += f"\nFILE: {path}\n```\n{content}\n```\n"

    return f"""Recommendation:
Title: {recommendation['title']}
Description: {recommendation['description']}
Primary File: {recommendation['file']}

Current Files Content:
{files_text}

Implement this recommendation and return the updated content for ALL involved files.
Also provide explanations for the major change blocks.
"""
