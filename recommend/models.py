from dataclasses import dataclass, field
from typing import Literal

@dataclass
class Recommendation:
    id: str
    title: str
    level: Literal["Easy", "Medium", "Hard"]
    description: str
    file: str
    files: list[str] = field(default_factory=list)
    rationale: str | None = None
    risks: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Recommendation":
        # Ensure 'files' is present
        if "files" not in data and "file" in data:
            data["files"] = [data["file"]]
        return cls(**data)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "level": self.level,
            "description": self.description,
            "file": self.file,
            "files": self.files,
            "rationale": self.rationale,
            "risks": self.risks
        }
