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

    # explain: explain a symbol, file, or query using the local LLM
    explain_parser = subparsers.add_parser(
        "explain", help="Explain code using the local LLM"
    )
    explain_parser.add_argument(
        "target", nargs="?",
        help="File path, qualified name (e.g. 'Job.run'), or natural-language query"
    )
    explain_parser.add_argument(
        "--all", action="store_true",
        help="Explain every symbol in the DB and cache results"
    )
    explain_parser.add_argument(
        "--fresh", action="store_true",
        help="Ignore cached explanations and regenerate"
    )

    args = parser.parse_args()
    config: AppConfig = load_config()

    if args.command == "setup":
        # Pass embed_dim so the VECTOR column is created with the right dimension.
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
        engine = IngestionEngine(args.repo_dir, db_config)
        engine.run()

    elif args.command == "embed":
        from ingestion.database import DatabaseManager
        from llm.client import LLMClient
        from search.embeddings import EmbeddingEngine

        db = DatabaseManager(config.db)
        db.connect()
        # LLMClient now takes separate llm and embed configs.
        client = LLMClient(config.llm, config.embed)
        try:
            EmbeddingEngine(db, client, config.embed).run(force=args.force)
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
        retriever = Retriever(db, client)
        engine = ExplainEngine(db, client, retriever)
        try:
            if args.all:
                engine.explain_all(fresh=args.fresh)
            elif args.target:
                engine.explain(args.target, fresh=args.fresh)
            else:
                explain_parser.print_help()
        finally:
            db.close()
            client.close()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

