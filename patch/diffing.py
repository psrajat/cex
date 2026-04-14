import difflib
import re
from .models import PatchHunkExplanation

def generate_unified_diff(old_text: str, new_text: str, filename: str) -> str:
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}"
    )
    return "".join(diff)

def parse_hunks(diff_text: str) -> list[dict]:
    """Parse a unified diff into hunks with line number ranges."""
    hunks = []
    current_hunk = None
    
    lines = diff_text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("@@"):
            if current_hunk:
                hunks.append(current_hunk)
            
            match = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
            if match:
                old_start, old_len, new_start, new_len = match.groups()
                current_hunk = {
                    "header": line,
                    "old_start": int(old_start),
                    "old_len": int(old_len) if old_len else 1,
                    "new_start": int(new_start),
                    "new_len": int(new_len) if new_len else 1,
                    "lines": []
                }
        elif current_hunk:
            current_hunk["lines"].append(line)
            
    if current_hunk:
        hunks.append(current_hunk)
        
    return hunks

def map_explanations_to_hunks(hunks: list[dict], raw_explanations: list[dict]) -> list[PatchHunkExplanation]:
    """Simple mapping: if an explanation's region_hint is found in or near a hunk, or just sequential."""
    # For v1, we'll try a simple heuristic: match region_hint in the hunk's added lines
    # or just distribute them if hunk count matches explanation count.
    # A more robust way would be asking the LLM to provide line numbers.
    # Since we asked for FULL file content, we'll just try to find the explanation's 
    # context in the diff.
    
    results = []
    
    for i, hunk in enumerate(hunks):
        # Default behavior: if we have explanations, take the i-th one
        explanation_text = "Generated change."
        if i < len(raw_explanations):
            explanation_text = raw_explanations[i]["explanation"]
            
        old_lines = []
        new_lines = []
        curr_old = hunk["old_start"]
        curr_new = hunk["new_start"]
        
        for line in hunk["lines"]:
            if line.startswith("-"):
                old_lines.append(curr_old)
                curr_old += 1
            elif line.startswith("+"):
                new_lines.append(curr_new)
                curr_new += 1
            else:
                curr_old += 1
                curr_new += 1
                
        results.append(PatchHunkExplanation(
            hunk_header=hunk["header"],
            explanation=explanation_text,
            affected_lines_old=old_lines,
            affected_lines_new=new_lines
        ))
        
    return results

def format_explained_diff(diff_text: str, hunk_explanations: list[PatchHunkExplanation]) -> str:
    """Interleave explanations into the diff text using [EXPLANATION]: tags."""
    lines = diff_text.splitlines()
    output = []
    hunk_idx = 0
    
    for line in lines:
        output.append(line)
        if line.startswith("@@") and hunk_idx < len(hunk_explanations):
            output.append(f"[EXPLANATION]: {hunk_explanations[hunk_idx].explanation}")
            hunk_idx += 1
            
    return "\n".join(output)
