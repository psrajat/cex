import argparse
from setup_db import setup_database, reset_database
from ingestion.engine import IngestionEngine
from config import load_config, DBConfig


def main():
    parser = argparse.ArgumentParser(description="cex - Code EXplainer")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # setup: create the database and apply the schema idempotently
    subparsers.add_parser("setup", help="Initialise the cex database")

    # reset: truncate all data, keep schema intact
    subparsers.add_parser(
        "reset",
        help="Truncate all data from every table (schema is preserved)",
    )

    # ingest: parse a repository and populate the database
    ingest_parser = subparsers.add_parser(
        "ingest", help="Analyse and ingest a repository"
    )
    ingest_parser.add_argument("repo_dir", help="Path to the repository to analyse")
    ingest_parser.add_argument("--db-host", default=None)
    ingest_parser.add_argument("--db-name", default=None)
    ingest_parser.add_argument("--db-user", default=None)
    ingest_parser.add_argument("--db-password", default=None)

    args = parser.parse_args()
    config = load_config()  # defaults from config.toml

    if args.command == "setup":
        setup_database(config)

    elif args.command == "reset":
        reset_database(config)

    elif args.command == "ingest":
        db_config = DBConfig(
            host=args.db_host or config.host,
            name=args.db_name or config.name,
            user=args.db_user or config.user,
            password=args.db_password or config.password,
        )
        engine = IngestionEngine(args.repo_dir, db_config)
        engine.run()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
