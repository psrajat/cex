from pathlib import Path
from .models import RepoMap
import re

class RepoMapWriter:
    """Renders the RepoMap data class into the final markdown format."""

    def write(self, repo_map: RepoMap, output_path: Path) -> Path:
        lines = ["# 🗺️ Repository Map\n"]

        # 1. Repo Summary
        lines.append("## 1. 📊 Repo Summary")
        for key, val in repo_map.summary.items():
            lines.append(f"- **{key}**: {val}")
        lines.append("")

        # 2. Main Subsystems
        lines.append("## 2. 🏗️ Main Subsystems")
        for sub in repo_map.subsystems:
            lines.append(f"- 📁 **`{sub.name}/`**")
            lines.append(f"  > {sub.description.strip()}")
        lines.append("")

        # 3. Important Files (Includes Symbols)
        lines.append("## 3. 📄 Important Files & Symbols")
        for f in repo_map.important_files:
            lines.append(f"\n### `{f.path}`")
            lines.append(f"- **Role**: {f.role.strip()}")
            lines.append(f"- **Importance**: {f.why_it_matters.strip()}")
            
            if f.explanation:
                exp_clean = f.explanation.replace('\n', ' ').strip()
                lines.append(f"  > {exp_clean}")
            
            if f.symbols:
                lines.append("\n  **🔑 Key Symbols:**")
                for sym in f.symbols:
                    sig_str = f" `{sym.signature}`" if sym.signature else ""
                    lines.append(f"  - 🧩 **`{sym.name}`** ({sym.type}){sig_str}")
                    if sym.explanation:
                        sym_exp_clean = sym.explanation.replace('\n', ' ').strip()
                        lines.append(f"    > {sym_exp_clean}")
        lines.append("")

        # 4. Suggested Reading Paths
        lines.append("## 4. 🛤️ Suggested Reading Paths")
        for path in repo_map.reading_paths:
            lines.append(f"- ➡️ {path}")
        lines.append("")

        # 5. Known Gaps / Limitations
        lines.append("## 5. ⚠️ Known Gaps / Limitations")
        for gap in repo_map.gaps:
            lines.append(f"- {gap}")
        lines.append("")

        # Save to disk
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        
        return output_path
