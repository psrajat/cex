from dataclasses import dataclass, field


@dataclass(frozen=True)
class DependencyModel:
    name: str
    version: str
    manifest_file: str
    language: str


@dataclass(frozen=True)
class FileModel:
    path: str
    extension: str
    language: str  # e.g. 'python' — used for display and future multi-language routing


@dataclass
class SymbolModel:
    """
    A named, addressable unit of code (class, function, endpoint, or ORM model).
    Variables, constants, and decorators live inside a symbol's code_body and are
    not indexed separately — they are read as context by the LLM.

    Types:
      class    — class, interface, struct, trait
      function — function, method (including async)
      endpoint — HTTP/gRPC/event handler identified by a framework decorator
      model    — ORM/schema class identified by a known base class
    """
    file_path: str          # relative path; used to join against files.path
    qualified_name: str     # e.g. "httpie.core.main" or "MyClass.my_method"
    type: str               # 'class' | 'function' | 'endpoint' | 'model'
    name: str
    signature: str          # first source line of the definition
    code_body: str          # full source text (contains all nested detail)
    start_line: int         # 1-based; needed by the PR diff generator
    end_line: int           # 1-based
    metadata: dict = field(default_factory=dict)  # JSONB extras, type-specific


@dataclass(frozen=True)
class RelationModel:
    source_qname: str   # fully-qualified name of the source symbol
    target_qname: str   # fully-qualified name of the target symbol
    relation_type: str  # 'NESTED_IN' | 'CALLS' | 'IMPORTS' | 'ROUTES_TO'
