# cex - Code EXplainer (Ingestion Engine)

A local-first tool to build a semantic and relational index of your codebases.

## Requirements

- Python 3.12+
- PostgreSQL

## Installation

Ensure you have `uv` installed, then run:

```bash
uv sync
```

## Usage

### 1. Initialize the Database

This will create the `cex` database and the necessary tables (`files`, `auls`, `relations`, `dependencies`).

```bash
uv run python main.py setup
```

### 2. Ingest a Repository

Analyze a local directory and store its structure and logic in the database.

```bash
uv run python main.py ingest /path/to/your/repo
```

#### Options:
- `--db-host`: PostgreSQL host (default: `localhost`)
- `--db-name`: Database name (default: `cex`)
- `--db-user`: Database user (default: `postgres`)
- `--db-password`: Database password
- `--dry-run`: Run in dry-run mode (prints actions without writing to DB)

## Architecture

The engine uses a **Tiered Intelligence** approach:
- **Shallow Indexing:** Scans manifest files (`requirements.txt`, `pyproject.toml`) to track dependencies.
- **Deep Indexing:** Uses `tree-sitter` to parse Python code into **Atomic Units of Logic (AULs)** (classes, functions).
- **Relational Mapping:** Maps structural relationships (e.g., nesting, inheritance) into a PostgreSQL graph.
