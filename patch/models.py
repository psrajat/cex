from dataclasses import dataclass
from typing import List

@dataclass
class PatchHunkExplanation:
    hunk_header: str
    explanation: str
    affected_lines_new: List[int]
    affected_lines_old: List[int]

@dataclass
class PatchResult:
    recommendation_id: str
    diff_text: str
    explained_diff_text: str
    hunks: List[PatchHunkExplanation]
    files: List[str]
    file_patches: List[dict]  # list of {path: str, old: str, new: str}

    def to_dict(self) -> dict:
        return {
            "recommendation_id": self.recommendation_id,
            "diff_text": self.diff_text,
            "explained_diff_text": self.explained_diff_text,
            "hunks": [
                {
                    "hunk_header": h.hunk_header,
                    "explanation": h.explanation,
                    "affected_lines_new": h.affected_lines_new,
                    "affected_lines_old": h.affected_lines_old,
                }
                for h in self.hunks
            ],
            "files": self.files,
            "file_patches": self.file_patches
        }
