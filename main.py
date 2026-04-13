import argparse
from setup_db import setup_database, reset_database
from ingestion.engine import IngestionEngine
from config import load_config, DBConfig, AppConfig


def main():
    parser = argparse.ArgumentParser(description="cex - Code EXplainer")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # setup: create the database and apply the schema idempotently
    subparsers.add_parser("setup", help="Initialise the cex database")

    # reset: drop and recreate the database
    subparsers.add_parser("reset", help="Drop and recreate the database")

    # ingest: parse a repository and populate the database
    ingest_parser = subparsers.add_parser(
        "ingest", help="Analyse and ingest a repository"
    )
    ingest_parser.add_argument("repo_dir", help="Path to the repository to analyse")
    ingest_parser.add_argument("--db-host", default=None)
    ingest_parser.add_argument("--db-name", default=None)
    ingest_parser.add_argument("--db-user", default=None)
    ingest_parser.add_argument("--db-password", default=None)

    # embed: generate vector embeddings for all ingested symbols
    embed_parser = subparsers.add_parser(
        "embed", help="Generate embeddings for all symbols"
    )
    embed_parser.add_argument(
        "--force", action="store_true",
        help="Re-embed all symbols even if already embedded"
    )

    # build: pre-generate and cache LLM explanations (no output displayed)
    # Run this once after ingestion to warm the explanation cache.
    build_parser = subparsers.add_parser(
        "build", help="Pre-generate and cache LLM explanations"
    )
    build_parser.add_argument(
        "target", nargs="?",
        help="File path, qualified name, or query (omit to build all symbols)"
    )
    build_parser.add_argument(
        "--fresh", action="store_true",
        help="Regenerate even if an explanation is already cached"
    )

    # explain: query the explanation for a symbol (generates on-demand if not cached)
    explain_parser = subparsers.add_parser(
        "explain", help="Show the explanation for a symbol (generates if not cached)"
    )
    explain_parser.add_argument(
        "target",
        help="File path, qualified name (e.g. 'Job.run'), or natural-language query"
    )

    # server: start the FastAPI + Vite UI server
    server_parser = subparsers.add_parser(
        "server", help="Start the cex API server (serves the React UI in production)"
    )
    server_parser.add_argument(
        "--host", default="127.0.0.1",
        help="Interface to bind (default: 127.0.0.1)"
    )
    server_parser.add_argument(
        "--port", type=int, default=8000,
        help="Port to listen on (default: 8000)"
    )
    server_parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload on code changes (development mode)"
    )

    args = parser.parse_args()
    config: AppConfig = load_config()

    if args.command == "setup":
        setup_database(config.db, embed_dim=config.embed.dim)

    elif args.command == "reset":
        reset_database(config.db, embed_dim=config.embed.dim)

    elif args.command == "ingest":
        db_config = DBConfig(
            host=args.db_host or config.db.host,
            name=args.db_name or config.db.name,
            user=args.db_user or config.db.user,
            password=args.db_password or config.db.password,
        )
        IngestionEngine(args.repo_dir, db_config).run()

    elif args.command == "embed":
        from ingestion.database import DatabaseManager
        from llm.client import LLMClient
        from search.embeddings import EmbeddingEngine

        db = DatabaseManager(config.db)
        db.connect()
        client = LLMClient(config.llm, config.embed)
        try:
            EmbeddingEngine(db, client, config.embed).run(force=args.force)
        finally:
            db.close()
            client.close()

    elif args.command == "build":
        from ingestion.database import DatabaseManager
        from llm.client import LLMClient
        from search.retriever import Retriever
        from explain.engine import ExplainEngine

        db = DatabaseManager(config.db)
        db.connect()
        client = LLMClient(config.llm, config.embed)
        engine = ExplainEngine(db, client, Retriever(db, client), log_cfg=config.logging)
        try:
            if args.target:
                engine.build(args.target, fresh=args.fresh)
            else:
                engine.build_all(fresh=args.fresh)
        finally:
            db.close()
            client.close()

    elif args.command == "explain":
        from ingestion.database import DatabaseManager
        from llm.client import LLMClient
        from search.retriever import Retriever
        from explain.engine import ExplainEngine

        db = DatabaseManager(config.db)
        db.connect()
        client = LLMClient(config.llm, config.embed)
        engine = ExplainEngine(db, client, Retriever(db, client), log_cfg=config.logging)
        try:
            engine.query(args.target)
        finally:
            db.close()
            client.close()

    elif args.command == "server":
        import uvicorn
        uvicorn.run(
            "api.server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

