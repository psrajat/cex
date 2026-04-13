from contextlib import closing
import psycopg2


# Ordered DDL applied to the cex database on every setup run.
# Every statement is idempotent (CREATE IF NOT EXISTS / DO NOTHING).
_DDL: list[str] = [
    # pgvector extension — shipped in the pgvector/pgvector Docker image.
    # Required for the VECTOR column added to symbols in Phase 3 (cex embed).
    "CREATE EXTENSION IF NOT EXISTS vector",

    # files: one row per source file discovered during ingestion.
    # id = relative path (e.g. 'schedule/__init__.py') — human-readable PK.
    # `language` drives parser routing for future multi-language support.
    """CREATE TABLE IF NOT EXISTS files (
        id        TEXT PRIMARY KEY,  -- relative path within the ingested repo
        extension TEXT,
        language  TEXT NOT NULL DEFAULT 'python'
    )""",

    # symbols: every class, function, endpoint, or ORM model extracted by
    # tree-sitter.  Variables/constants are NOT indexed — they live inside
    # a symbol's code_body and are provided as LLM context, not queried directly.
    #
    # Types: 'class' | 'function' | 'endpoint' | 'model'
    # Relations: 'NESTED_IN' | 'CALLS' | 'IMPORTS' | 'ROUTES_TO'
    #
    # The `embedding` VECTOR column is added in Phase 3 (cex embed).
    """CREATE TABLE IF NOT EXISTS symbols (
        id             TEXT PRIMARY KEY,  -- qualified_name, e.g. 'httpie.core.main'
        file_id        TEXT REFERENCES files(id) ON DELETE CASCADE,
        type           TEXT,
        name           TEXT,
        qualified_name TEXT,
        signature      TEXT,       -- first line of the definition
        code_body      TEXT,
        start_line     INT,        -- 1-based; used by the PR diff generator
        end_line       INT,        -- 1-based
        metadata       JSONB DEFAULT '{}'  -- type-specific extras (method, bases, …)
    )""",

    # relations: directed edges between symbols.
    # id = '{source_id}::{relation_type}::{target_id}' — no UUID needed.
    """CREATE TABLE IF NOT EXISTS relations (
        id               TEXT PRIMARY KEY,  -- '{src}::{type}::{tgt}'
        source_symbol_id TEXT REFERENCES symbols(id) ON DELETE CASCADE,
        target_symbol_id TEXT REFERENCES symbols(id) ON DELETE CASCADE,
        relation_type    TEXT   -- 'NESTED_IN' | 'CALLS' | 'IMPORTS' | 'ROUTES_TO'
    )""",

    # repo_info: one row per ingested repository.
    # Provides repo-level context for the LLM (entry points, primary language, etc.).
    # id = absolute root path of the repository.
    """CREATE TABLE IF NOT EXISTS repo_info (
        id          TEXT PRIMARY KEY,  -- absolute root path
        language    TEXT NOT NULL,
        ingested_at TIMESTAMPTZ DEFAULT now(),
        metadata    JSONB DEFAULT '{}'
    )""",

    # dependencies: packages detected from manifest files (requirements.txt, pyproject.toml …).
    # id = '{manifest_file}::{name}' — unique per manifest.
    """CREATE TABLE IF NOT EXISTS dependencies (
        id            TEXT PRIMARY KEY,  -- '{manifest_file}::{name}'
        name          TEXT NOT NULL,
        version       TEXT,
        manifest_file TEXT NOT NULL,
        language      TEXT NOT NULL
    )""",

    # file_imports: module-level import statements from each source file.
    # Used by the Flow Tracer to follow cross-file dependency chains.
    # `names` contains what was imported (e.g. ['Path', 'PurePath']);
    # empty for bare `import os` style.
    # id = '{file_id}::{module}' — one row per (file, module) pair.
    """CREATE TABLE IF NOT EXISTS file_imports (
        id      TEXT PRIMARY KEY,  -- '{file_id}::{module}'
        file_id TEXT REFERENCES files(id) ON DELETE CASCADE,
        module  TEXT NOT NULL,
        names   TEXT[] DEFAULT '{}'
    )""",

    # explanations: cached LLM-generated explanation for each symbol.
    # id = symbols.id (qualified_name).  Decoupled from symbols table so
    # schema migrations on symbols don't cascade-delete expensive LLM output.
    """CREATE TABLE IF NOT EXISTS explanations (
        id           TEXT PRIMARY KEY,  -- = symbols.id (qualified_name)
        text         TEXT NOT NULL,
        generated_at TIMESTAMPTZ DEFAULT now()
    )""",
]


def setup_database(db_config, embed_dim: int = 768) -> None:
    """Create the cex database (if absent) and apply the schema idempotently.

    ``embed_dim`` must match the output dimension of the configured embedding
    model (see ``[embed] dim`` in config.toml).  It is used to create the
    ``VECTOR(N)`` column on the symbols table and the HNSW index.

    All DDL statements are idempotent — safe to run on an already-initialised
    database (e.g. after a config change that doesn't require a full reset).
    """
    conn_kwargs = dict(
        host=db_config.host, user=db_config.user, password=db_config.password
    )

    # Connect to the default 'postgres' DB to issue CREATE DATABASE if needed.
    # Docker Compose already creates cex via POSTGRES_DB=cex, but this also
    # handles bare PostgreSQL installs.
    with closing(psycopg2.connect(dbname="postgres", **conn_kwargs)) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (db_config.name,)
            )
            if cur.fetchone():
                print(f"Database '{db_config.name}' already exists.")
            else:
                print(f"Creating database '{db_config.name}'…")
                # Database names cannot be parameterised; db_config.name comes
                # from the trusted config file, not from user-supplied input.
                cur.execute(f"CREATE DATABASE {db_config.name}")

    # Apply each DDL statement to the target database.
    with closing(psycopg2.connect(dbname=db_config.name, **conn_kwargs)) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("Initialising tables…")
            for stmt in _DDL:
                cur.execute(stmt)

            # Add the embedding vector column and its HNSW index.
            # Done here (not in _DDL) because the dimension comes from config,
            # not the static schema.  Both statements are idempotent.
            cur.execute(
                f"ALTER TABLE symbols "
                f"ADD COLUMN IF NOT EXISTS embedding VECTOR({embed_dim})"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS symbols_embedding_hnsw_idx "
                "ON symbols USING hnsw (embedding vector_cosine_ops)"
            )

    print("Database setup complete.")


def reset_database(db_config, embed_dim: int = 768) -> None:
    """Drop and recreate the cex database, applying the full schema fresh.

    Use this before re-ingesting a repository from scratch.
    WARNING: all data is permanently deleted.
    """
    conn_kwargs = dict(
        host=db_config.host, user=db_config.user, password=db_config.password
    )
    # Must connect to `postgres` — cannot drop the DB we're currently in.
    with closing(psycopg2.connect(dbname="postgres", **conn_kwargs)) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Terminate any open connections to the target DB first;
            # DROP DATABASE fails if sessions are active.
            cur.execute(
                "SELECT pg_terminate_backend(pid)"
                " FROM pg_stat_activity"
                " WHERE datname = %s AND pid <> pg_backend_pid()",
                (db_config.name,),
            )
            cur.execute(f"DROP DATABASE IF EXISTS {db_config.name}")
            cur.execute(f"CREATE DATABASE {db_config.name}")
            print(f"Database '{db_config.name}' recreated.")

    # Re-apply the full schema to the fresh database.
    setup_database(db_config, embed_dim=embed_dim)


if __name__ == "__main__":
    from config import load_config

    cfg = load_config()
    setup_database(cfg.db, embed_dim=cfg.embed.dim)
