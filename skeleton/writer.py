from pathlib import Path
from .models import RepoMap

class RepoMapWriter:
    """Renders the RepoMap data class into the final markdown format."""

    def write(self, repo_map: RepoMap, output_path: Path) -> Path:
        lines = ["# Repository Map\n"]

        # 1. Repo Summary
        lines.append("## 1. Repo Summary")
        for key, val in repo_map.summary.items():
            lines.append(f"- {key}: {val}")
        lines.append("")

        # 2. Main Subsystems
        lines.append("## 2. Main Subsystems")
        for sub in repo_map.subsystems:
            lines.append(f"- {sub.name}/: {sub.description}")
        lines.append("")

        # 3. Important Files
        lines.append("## 3. Important Files")
        for f in repo_map.important_files:
            lines.append(f"\n### {f.path}")
            lines.append(f"Role: {f.role}")
            lines.append("Why it matters:")
            lines.append(f"- {f.why_it_matters}")
            
            # Key symbols (names only)
            if f.symbols:
                lines.append("Key symbols:")
                sym_names = [sym.name for sym in f.symbols]
                lines.append(f"- {', '.join(sym_names)}")
            
            if f.explanation:
                lines.append("Known explanation:")
                lines.append(f"- {f.explanation}")
        lines.append("")

        # 4. Important Symbols by File
        lines.append("## 4. Important Symbols by File")
        for f in repo_map.important_files:
            if not f.symbols:
                continue
            lines.append(f"\n### {f.path}")
            for sym in f.symbols:
                lines.append(f"- {sym.name} [{sym.type}]")
                if sym.explanation:
                    lines.append(f"  - {sym.explanation}")
        lines.append("")

        # 5. Suggested Reading Paths
        lines.append("## 5. Suggested Reading Paths")
        for path in repo_map.reading_paths:
            lines.append(f"- {path}")
        lines.append("")

        # 6. Known Gaps / Limitations
        lines.append("## 6. Known Gaps / Limitations")
        for gap in repo_map.gaps:
            lines.append(f"- {gap}")
        lines.append("")

        # Save to disk
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        
        return output_path
