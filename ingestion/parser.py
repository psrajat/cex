"""ingestion/parser.py

Language-agnostic code parser built on tree-sitter.

Adding a new language requires:
  1. `pip install tree-sitter-<lang>`
  2. A `LangSpec` entry in `_LANG_SPECS` (node type names + 4 extractors)
  3. Nothing else — CodeParser routes by file extension automatically.
"""

import re
import tomli
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from tree_sitter import Language, Node, Parser
import tree_sitter_python as tspython

from .models import DependencyModel, FileModel, SymbolModel, RelationModel

_SKIP_DIRS = frozenset({"venv", ".venv", "__pycache__", ".git", "node_modules", "tests", "test"})
# Test files are excluded from indexing — they explain behaviour, not the code itself.
_TEST_FILE_RE = re.compile(r"^(test_|.*_test\.py$|conftest\.py$)")


# ── Language spec (data-only) ─────────────────────────────────────────────────

@dataclass(frozen=True)
class LangSpec:
    ts_parser:        Parser
    lang:             str                  # 'python', 'typescript', …
    file_glob:        str                  # '*.py', '*.ts', …
    symbol_types:     frozenset[str]       # AST node types → SymbolModel rows
    call_type:        str                  # AST node type for call expressions
    import_types:     frozenset[str]       # AST node types for import statements
    get_name:         Callable[[Node, str], str | None]
    classify:         Callable[[Node, str], tuple[str, dict]]  # → (type, metadata)
    get_callee:       Callable[[Node, str], str | None]
    parse_import:     Callable[[Node, str], tuple[str, list[str]] | None]
    module_prefix:    Callable[[str], str]  # rel_path → dotted module prefix


# ── Python implementation ─────────────────────────────────────────────────────

_PY_ENDPOINT_KW = frozenset(
    {"get", "post", "put", "delete", "patch", "head", "options", "route", "websocket"}
)
_PY_MODEL_BASES = frozenset(
    {"Base", "BaseModel", "Model", "DeclarativeBase", "db.Model", "Document", "SQLModel"}
)


def _py_get_name(node: Node, src: str) -> str | None:
    n = node.child_by_field_name("name")
    return src[n.start_byte : n.end_byte] if n else None


def _py_classify(node: Node, src: str) -> tuple[str, dict]:
    if node.type == "function_definition":
        meta: dict = {}
        if src[node.start_byte : node.start_byte + 5] == "async":
            meta["is_async"] = True
        parent = node.parent
        decs = (
            [src[c.start_byte : c.end_byte][1:] for c in parent.children if c.type == "decorator"]
            if parent and parent.type == "decorated_definition" else []
        )
        for dec in decs:
            kw = next((k for k in _PY_ENDPOINT_KW if f".{k}" in dec.lower()), None)
            if kw:
                return "endpoint", {**meta, "method": kw.upper(), "decorators": decs}
        return "function", meta
    # class_definition
    sc = node.child_by_field_name("superclasses")
    bases = (
        [src[c.start_byte : c.end_byte] for c in sc.children if c.type in ("identifier", "attribute")]
        if sc else []
    )
    return ("model" if any(b in _PY_MODEL_BASES for b in bases) else "class"), ({"bases": bases} if bases else {})


def _py_get_callee(node: Node, src: str) -> str | None:
    """Extract the called function name from a call expression node.

    Handles both simple calls (``foo()``) and attribute/method calls
    (``obj.method()``).  Returns just the leaf name — qualified name
    resolution happens later in the CALLS walk using qname_map.
    """
    fn = node.child_by_field_name("function")
    if fn and fn.type == "identifier":
        return src[fn.start_byte : fn.end_byte]
    if fn and fn.type == "attribute":
        attr = fn.child_by_field_name("attribute")
        return src[attr.start_byte : attr.end_byte] if attr else None
    return None


def _py_parse_import(node: Node, src: str) -> tuple[str, list[str]] | None:
    """Extract (module_name, [imported_names]) from an import AST node.

    ``import os``            → ('os', [])
    ``import os as o``       → ('os', [])
    ``from os.path import join, exists`` → ('os.path', ['join', 'exists'])
    ``from pkg import *``    → ('pkg', ['*'])
    Returns None if the node cannot be parsed.
    """
    if node.type == "import_statement":
        for c in node.children:
            if c.type in ("dotted_name", "identifier"):
                return src[c.start_byte : c.end_byte], []
            if c.type == "aliased_import":
                n = c.child_by_field_name("name")
                return (src[n.start_byte : n.end_byte], []) if n else None
    if node.type == "import_from_statement":
        mn = node.child_by_field_name("module_name")
        module = src[mn.start_byte : mn.end_byte] if mn else "?"
        names: list[str] = []
        for c in node.children:
            if c == mn:
                continue
            if c.type == "wildcard_import":
                names.append("*")
            elif c.type == "import_list":
                for item in c.children:
                    if item.type in ("dotted_name", "identifier"):
                        names.append(src[item.start_byte : item.end_byte])
                    elif item.type == "aliased_import":
                        n = item.child_by_field_name("name")
                        if n:
                            names.append(src[n.start_byte : n.end_byte])
        return module, names
    return None


# ── Language registry — add new languages here ────────────────────────────────

_LANG_SPECS: dict[str, LangSpec] = {
    ".py": LangSpec(
        ts_parser=Parser(Language(tspython.language())),
        lang="python", file_glob="*.py",
        symbol_types=frozenset({"class_definition", "function_definition"}),
        call_type="call",
        import_types=frozenset({"import_statement", "import_from_statement"}),
        get_name=_py_get_name, classify=_py_classify,
        get_callee=_py_get_callee, parse_import=_py_parse_import,
        module_prefix=lambda p: p.removesuffix(".py").replace("/", ".").replace("\\", "."),
    ),
}


# ── CodeParser ────────────────────────────────────────────────────────────────

class CodeParser:
    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir

    def parse_manifests(self) -> list[DependencyModel]:
        """Scan requirements.txt and pyproject.toml for declared dependencies."""
        print("Scanning manifests…")
        deps: list[DependencyModel] = []

        req = self.repo_dir / "requirements.txt"
        if req.exists():
            pat = re.compile(r"^([a-zA-Z0-9\-_.]+)[>=<!]+([0-9][0-9a-zA-Z.*,]+)")
            for line in req.read_text().splitlines():
                m = pat.match(line.strip())
                if m:
                    deps.append(DependencyModel(name=m.group(1), version=m.group(2),
                                                manifest_file="requirements.txt", language="python"))

        pyproject = self.repo_dir / "pyproject.toml"
        if pyproject.exists():
            try:
                data = tomli.loads(pyproject.read_text())
                for dep in data.get("project", {}).get("dependencies", []):
                    parts = re.split(r"[>=<!\[]", dep, 1)
                    deps.append(DependencyModel(
                        name=parts[0].strip(),
                        version=parts[1].strip() if len(parts) > 1 else "latest",
                        manifest_file="pyproject.toml", language="python",
                    ))
            except Exception as e:
                print(f"Warning: could not parse {pyproject}: {e}")

        return deps

    def parse_files(self) -> list[FileModel]:
        """Discover all source files for every registered language."""
        print("Scanning files…")
        files: list[FileModel] = []
        for ext, spec in _LANG_SPECS.items():
            files += [
                FileModel(path=str(p.relative_to(self.repo_dir)), extension=ext, language=spec.lang)
                for p in self.repo_dir.rglob(spec.file_glob)
                if not _SKIP_DIRS.intersection(p.parts)
                and not _TEST_FILE_RE.match(p.name)
            ]
        return files

    def parse_symbols_and_relations(
        self, file_path: Path
    ) -> tuple[list[SymbolModel], list[RelationModel], list[tuple[str, list[str]]]]:
        """Analyse one file.  Returns (symbols, relations, imports).

        relations — NESTED_IN + CALLS (intra-file)
        imports   — list of (module, [imported_names])
        """
        spec = _LANG_SPECS.get(file_path.suffix)
        if spec is None:
            return [], [], []

        try:
            src = file_path.read_text(encoding="utf-8", errors="replace")
            tree = spec.ts_parser.parse(bytes(src, "utf-8"))
        except Exception as e:
            print(f"  Warning: {file_path.name}: {e}")
            return [], [], []

        rel_path = str(file_path.relative_to(self.repo_dir))
        mod_prefix = spec.module_prefix(rel_path)

        symbols:   list[SymbolModel]           = []
        relations: list[RelationModel]          = []
        imports:   list[tuple[str, list[str]]]  = []
        seen_calls: set[tuple[str, str]]        = set()

        # Pre-pass: build name → qualified_name map so CALLS can resolve callees.
        # When the same simple name appears in multiple scopes, the outermost wins;
        # this is accurate enough for intra-file CALLS in v1.
        qname_map: dict[str, str] = {}
        def _pre(node: Node, prefix: str) -> None:
            if node.type in spec.symbol_types:
                name = spec.get_name(node, src)
                if name and name not in qname_map:
                    qname = f"{prefix}.{name}" if prefix else f"{mod_prefix}.{name}"
                    qname_map[name] = qname
                    for c in node.children:
                        _pre(c, qname)
                    return
            for c in node.children:
                _pre(c, prefix)
        _pre(tree.root_node, mod_prefix)

        # Main walk: emit symbols, NESTED_IN, CALLS, and imports together.
        def _walk(node: Node, parent: SymbolModel | None, caller_qname: str | None) -> None:
            if node.type in spec.import_types:
                parsed = spec.parse_import(node, src)
                if parsed:
                    imports.append(parsed)
                return

            if node.type in spec.symbol_types:
                name = spec.get_name(node, src)
                if name:
                    sym_type, meta = spec.classify(node, src)
                    qname = f"{parent.qualified_name}.{name}" if parent else f"{mod_prefix}.{name}"
                    sym = SymbolModel(
                        file_path=rel_path, qualified_name=qname, type=sym_type, name=name,
                        signature=src[node.start_byte : node.end_byte].split("\n")[0],
                        code_body=src[node.start_byte : node.end_byte],
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        metadata=meta,
                    )
                    symbols.append(sym)
                    if parent:
                        relations.append(RelationModel(
                            source_qname=parent.qualified_name,
                            target_qname=qname,
                            relation_type="NESTED_IN",
                        ))
                    for c in node.children:
                        _walk(c, sym, qname)  # this symbol is now the fn context
                    return

            if node.type == spec.call_type and caller_qname:
                callee_name = spec.get_callee(node, src)
                callee_qname = qname_map.get(callee_name) if callee_name else None
                if callee_qname and callee_qname != caller_qname:
                    key = (caller_qname, callee_qname)
                    if key not in seen_calls:
                        seen_calls.add(key)
                        relations.append(RelationModel(
                            source_qname=caller_qname,
                            target_qname=callee_qname,
                            relation_type="CALLS",
                        ))

            for c in node.children:
                _walk(c, parent, caller_qname)

        _walk(tree.root_node, None, None)
        return symbols, relations, imports
