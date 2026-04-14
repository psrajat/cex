"""api/server.py

FastAPI server that exposes cex data over HTTP and serves the React UI.

All symbol IDs (qualified names) are passed as query parameters to avoid
URL encoding issues with dots and underscores.

Endpoints:
  GET  /api/files                        list all ingested source files
  GET  /api/file-content?file=<path>     raw source text of a file
  GET  /api/symbols?file=<path>          symbols in a file (all if omitted)
  GET  /api/symbol?id=<qname>            one symbol by qualified name
  GET  /api/explanation?id=<qname>       cached explanation text (null if none)
  GET  /api/explain/stream?id=<qname>    stream explanation as SSE (generates if missing)
  POST /api/explain?id=<qname>           generate explanation silently (bulk/background use)
  GET  /api/callers?id=<qname>           symbols that call this one (CALLS in-edges)
  GET  /api/callees?id=<qname>           symbols this one calls (CALLS out-edges)
  GET  /api/parent?id=<qname>            enclosing class/function (NESTED_IN parent)
  GET  /api/search?q=<query>             semantic + keyword search

In production (after running `npm run build` in ui/), also serves the compiled
React app from ui/dist/ and falls back to index.html for all unmatched routes.
"""

import json
import os
from collections.abc import Generator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import load_config
from ingestion.database import DatabaseManager
from ingestion.models import SymbolModel
from llm.client import LLMClient
from llm.logger import log_prompt
from llm.prompts import build_explain_prompt
from search.retriever import Retriever
from explain.engine import ExplainEngine
from skeleton.engine import SkeletonEngine
from recommend.engine import RecommendationEngine
from patch.engine import PatchEngine

# ── Pydantic response models ──────────────────────────────────────────────────

class SymbolOut(BaseModel):
    id: str
    file_id: str
    type: str
    name: str
    qualified_name: str
    signature: str
    code_body: str
    start_line: int
    end_line: int
    metadata: dict


class FileOut(BaseModel):
    id: str
    extension: str
    language: str


class ExplanationOut(BaseModel):
    id: str
    text: str | None
    cached: bool


class FileContentOut(BaseModel):
    file: str       # relative path (same as files.id)
    content: str    # raw UTF-8 text
    language: str   # e.g. 'python'


class RecommendationOut(BaseModel):
    id: str
    title: str
    level: str
    description: str
    file: str
    files: list[str]
    rationale: str | None
    risks: list[str]


class PatchHunkOut(BaseModel):
    hunk_header: str
    explanation: str
    affected_lines_old: list[int]
    affected_lines_new: list[int]


class FilePatchOut(BaseModel):
    path: str
    old: str
    new: str

class PatchOut(BaseModel):
    recommendation_id: str
    files: list[str]
    diff_text: str
    explained_diff_text: str
    hunks: list[PatchHunkOut]
    file_patches: list[FilePatchOut]


class IngestRequest(BaseModel):
    repo_dir: str
    force: bool = False


# ── Shared state (initialised during lifespan) ────────────────────────────────

_ACTIVE_DB_FILE = Path("data/.active_db.json")

_db: DatabaseManager
_client: LLMClient
_retriever: Retriever
_engine: ExplainEngine
_skeleton_engine: SkeletonEngine
_recommendation_engine: RecommendationEngine
_patch_engine: PatchEngine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open DB + LLM connections once at startup; close them on shutdown."""
    from config import DBConfig
    
    cfg = load_config()
    db_config = cfg.db
    
    # Try to restore last active project
    if _ACTIVE_DB_FILE.exists():
        try:
            with open(_ACTIVE_DB_FILE, "r") as f:
                data = json.load(f)
                db_config = DBConfig(**data)
                print(f"Restoring project database: {db_config.name}")
        except Exception as e:
            print(f"Failed to restore active DB: {e}")
            
    _init_engines(db_config)
    yield
    global _db, _client
    if _db: _db.close()
    if _client: _client.close()

def _init_engines(db_config):
    """Rebind all global engines to point to the active database."""
    global _db, _client, _retriever, _engine, _skeleton_engine, _recommendation_engine, _patch_engine
    
    if '_db' in globals() and _db is not None:
        try: _db.close()
        except: pass
        
    if '_client' in globals() and _client is not None:
        try: _client.close()
        except: pass

    cfg = load_config()
    _db = DatabaseManager(db_config)
    _db.connect()
    _client = LLMClient(cfg.llm, cfg.embed)
    _retriever = Retriever(_db, _client)
    _engine = ExplainEngine(_db, _client, _retriever, log_cfg=cfg.logging)
    _skeleton_engine = SkeletonEngine(_db)
    _recommendation_engine = RecommendationEngine(_client, _skeleton_engine, log_cfg=cfg.logging)
    _patch_engine = PatchEngine(_client, _db, _recommendation_engine, log_cfg=cfg.logging)

    # Persist the choice
    try:
        from dataclasses import asdict
        _ACTIVE_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_ACTIVE_DB_FILE, "w") as f:
            json.dump(asdict(db_config), f)
    except Exception as e:
        print(f"Warning: Could not save active DB state: {e}")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="cex API", version="1.0.0", lifespan=lifespan)

# Allow the Vite dev server (port 5173) to call the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sym(s: SymbolModel) -> SymbolOut:
    return SymbolOut(
        id=s.qualified_name,
        file_id=s.file_path,
        type=s.type,
        name=s.name,
        qualified_name=s.qualified_name,
        signature=s.signature,
        code_body=s.code_body,
        start_line=s.start_line,
        end_line=s.end_line,
        metadata=s.metadata,
    )


def _require_symbol(symbol_id: str) -> SymbolModel:
    sym = _db.fetch_symbol(symbol_id)
    if not sym:
        raise HTTPException(status_code=404, detail=f"Symbol not found: {symbol_id!r}")
    return sym


# ── File endpoints ────────────────────────────────────────────────────────────

@app.get("/api/files", response_model=list[FileOut])
def list_files():
    """Return all ingested source files."""
    _db.cur.execute("SELECT id, extension, language FROM files ORDER BY id")
    rows = _db.cur.fetchall()
    return [FileOut(id=r[0], extension=r[1], language=r[2]) for r in rows]


@app.get("/api/file-content", response_model=FileContentOut)
def get_file_content(file: str = Query(..., description="Relative file path")):
    """Return the raw source text of an ingested file.

    Reads directly from disk using the repo root stored in repo_info.
    Path traversal is prevented by validating the resolved path stays
    within the known repo root.
    """
    # Verify the file exists in the DB.
    _db.cur.execute("SELECT language FROM files WHERE id = %s", (file,))
    row = _db.cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"File not ingested: {file!r}")
    language = row[0]

    # Retrieve the stored repo root.
    _db.cur.execute("SELECT id FROM repo_info LIMIT 1")
    repo_row = _db.cur.fetchone()
    if not repo_row:
        raise HTTPException(status_code=503, detail="No repo ingested yet")
    repo_root = Path(repo_row[0])

    # Build and validate the absolute path — prevent directory traversal.
    abs_path = (repo_root / file).resolve()
    if not abs_path.is_relative_to(repo_root.resolve()):
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found on disk: {file!r}")

    try:
        content = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return FileContentOut(file=file, content=content, language=language)


# ── Ingestion ─────────────────────────────────────────────────────────────────

@app.post("/api/ingest")
def ingest_repo(req: IngestRequest):
    """Swap the active database context to the requested repo. Overwrite if 'force' is checked."""
    from ingestion.engine import IngestionEngine
    from search.embeddings import EmbeddingEngine
    from config import DBConfig
    import setup_db
    import re
    import hashlib

    cfg = load_config()
    
    # Generate unique DB name for this repo
    clean_name = re.sub(r'[^a-z0-9]', '_', Path(req.repo_dir).name.lower())[:30]
    hash_suffix = hashlib.md5(req.repo_dir.encode("utf-8")).hexdigest()[:6]
    db_name = f"cex_{clean_name}_{hash_suffix}"

    try:
        db_config = DBConfig(
            host=cfg.db.host, name=db_name, user=cfg.db.user, password=cfg.db.password
        )
        
        if req.force:
            setup_db.reset_database(db_config, embed_dim=cfg.embed.dim)
        else:
            setup_db.setup_database(db_config, embed_dim=cfg.embed.dim)
        
        # Point API globals to the new project database instantly
        _init_engines(db_config)
        
        if req.force:
            # Reingest
            IngestionEngine(req.repo_dir, db_config).run()
            # We don't drop db inside here, _db is already connected
            EmbeddingEngine(_db, _client, cfg.embed).run(force=True)
            SkeletonEngine(_db).build(force=True)
            ExplainEngine(_db, _client, Retriever(_db, _client), log_cfg=cfg.logging).build_all(fresh=True)

        return {"ok": True, "message": f"Successfully loaded project in database {db_name}"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ── File System ────────────────────────────────────────────────────────────

@app.get("/api/fs/ls")
def list_directory(path: str = Query(..., description="Absolute path to list")):
    """List sub-directories for the file system picker."""
    p = Path(path)
    if not p.is_dir():
        return {"directories": []}
    
    try:
        dirs = [d.name for d in p.iterdir() if d.is_dir() and not d.name.startswith('.')]
        return {"directories": sorted(dirs)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Symbol endpoints ──────────────────────────────────────────────────────────

@app.get("/api/symbols", response_model=list[SymbolOut])
def list_symbols(file: str | None = Query(None, description="Filter by file path")):
    """Return all symbols, optionally filtered to a single source file."""
    syms = _db.fetch_symbols_by_file(file) if file else _db.fetch_all_symbols()
    return [_sym(s) for s in syms]


@app.get("/api/symbol", response_model=SymbolOut)
def get_symbol(id: str = Query(..., description="Qualified name")):
    return _sym(_require_symbol(id))


@app.get("/api/callers", response_model=list[SymbolOut])
def get_callers(id: str = Query(...)):
    """Symbols that call this one (inbound CALLS edges)."""
    return [_sym(s) for s in _db.fetch_related_symbols(id, "CALLS", direction="in")]


@app.get("/api/callees", response_model=list[SymbolOut])
def get_callees(id: str = Query(...)):
    """Symbols this one calls (outbound CALLS edges)."""
    return [_sym(s) for s in _db.fetch_related_symbols(id, "CALLS", direction="out")]


@app.get("/api/parent", response_model=SymbolOut | None)
def get_parent(id: str = Query(...)):
    """Enclosing class or function (NESTED_IN parent), or null."""
    parents = _db.fetch_related_symbols(id, "NESTED_IN", direction="in")
    return _sym(parents[0]) if parents else None


# ── Explanation endpoints ─────────────────────────────────────────────────────

@app.get("/api/explanation", response_model=ExplanationOut)
def get_explanation(id: str = Query(...)):
    """Return the cached explanation for a symbol, or null if not yet built."""
    _require_symbol(id)
    text = _db.fetch_explanation(id)
    return ExplanationOut(id=id, text=text, cached=text is not None)


@app.get("/api/explain/stream")
def stream_explanation(id: str = Query(...)):
    """Stream an LLM explanation as Server-Sent Events.

    If the explanation is already cached, the full text is sent in one event.
    Otherwise the LLM is called and tokens are forwarded as they arrive.
    The result is saved to the DB when the stream completes.
    """
    sym = _require_symbol(id)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # tell Nginx not to buffer SSE
    }

    # Cache hit: send all at once.
    cached = _db.fetch_explanation(id)
    if cached:
        def _cached_stream() -> Generator[str, None, None]:
            yield f"data: {cached.replace(chr(10), '\\n')}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(_cached_stream(), media_type="text/event-stream", headers=headers)

    # Cache miss: stream from LLM, collect, then persist.
    cfg = load_config()
    parent  = _retriever.get_parent(sym.qualified_name)
    callers = _retriever.get_callers(sym.qualified_name)
    callees = _retriever.get_callees(sym.qualified_name)
    messages = build_explain_prompt(sym, parent, callers, callees)
    log_prompt(messages, sym.qualified_name, cfg.logging)

    def _sse_stream() -> Generator[str, None, None]:
        parts: list[str] = []
        for token in _client.stream_chat(messages):
            parts.append(token)
            # Escape newlines so each SSE "data:" line is one logical message.
            escaped = token.replace("\n", "\\n")
            yield f"data: {escaped}\n\n"
        _db.save_explanation(sym.qualified_name, "".join(parts))
        yield "data: [DONE]\n\n"

    return StreamingResponse(_sse_stream(), media_type="text/event-stream", headers=headers)


@app.post("/api/explain", response_model=ExplanationOut)
def explain_symbol(id: str = Query(...)):
    """Generate an explanation silently (no streaming) and cache it.

    Use this for background pre-generation.  Prefer the /stream endpoint
    for interactive use so the user sees output immediately.
    """
    sym = _require_symbol(id)
    cached = _db.fetch_explanation(id)
    if cached:
        return ExplanationOut(id=id, text=cached, cached=True)
    text = _engine._generate(sym, stream=False)
    return ExplanationOut(id=id, text=text, cached=False)


# ── Search ────────────────────────────────────────────────────────────────────

@app.get("/api/search", response_model=list[SymbolOut])
def search(q: str = Query(..., min_length=1)):
    """Semantic + keyword search.  Requires `cex embed` to have been run for
    vector search; falls back to ILIKE keyword search if no embeddings exist."""
    return [_sym(s) for s in _retriever.search(q, k=15)]


# ── Recommendation endpoints ──────────────────────────────────────────────────

@app.get("/api/recommendations", response_model=list[RecommendationOut])
def list_recommendations():
    """Return the list of validated PR recommendations."""
    recs = _recommendation_engine.load()
    return [RecommendationOut(**r.to_dict()) for r in recs]


@app.post("/api/recommendations/refresh")
def refresh_recommendations():
    """Force rebuild the skeleton and regenerate all recommendations."""
    _skeleton_engine.build(force=True)
    recs = _recommendation_engine.generate(force=True)
    return {
        "ok": True,
        "count": len(recs),
        "skeleton_path": str(_skeleton_engine.output_path),
        "recommendations_path": str(_recommendation_engine.output_path)
    }


@app.get("/api/recommendations/patch", response_model=PatchOut)
def get_recommendation_patch(id: str = Query(..., description="Recommendation ID")):
    """Generate or retrieve the explained diff for a recommendation."""
    try:
        result = _patch_engine.generate(id)
        return PatchOut(
            recommendation_id=result.recommendation_id,
            files=result.files,
            diff_text=result.diff_text,
            explained_diff_text=result.explained_diff_text,
            hunks=[
                PatchHunkOut(
                    hunk_header=h.hunk_header,
                    explanation=h.explanation,
                    affected_lines_old=h.affected_lines_old,
                    affected_lines_new=h.affected_lines_new
                )
                for h in result.hunks
            ],
            file_patches=[
                FilePatchOut(path=p["path"], old=p["old"], new=p["new"])
                for p in result.file_patches
            ]
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/skeleton")
def get_skeleton():
    """Return the raw markdown skeleton."""
    return {"skeleton": _skeleton_engine.load()}


# ── Static file serving (production build) ───────────────────────────────────
# Mounted after all API routes so /api/* is never shadowed.

_UI_DIST = Path(__file__).parent.parent / "ui" / "dist"

if _UI_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIST), html=True), name="ui")
