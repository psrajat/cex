from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict

@dataclass
class RepoMapConfig:
    final_output_path: Path = Path("data/repo_map.md")
    max_files: int = 25
    max_symbols_per_file: int = 6

@dataclass
class EnrichedSymbol:
    name: str
    type: str
    signature: str
    explanation: Optional[str] = None
    score: float = 0.0

@dataclass
class EnrichedFile:
    path: str
    role: str
    why_it_matters: str
    symbols: List[EnrichedSymbol] = field(default_factory=list)
    explanation: Optional[str] = None
    score: float = 0.0

@dataclass
class Subsystem:
    name: str
    description: str

@dataclass
class RepoMap:
    summary: Dict[str, str] = field(default_factory=dict)
    subsystems: List[Subsystem] = field(default_factory=list)
    important_files: List[EnrichedFile] = field(default_factory=list)
    reading_paths: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
