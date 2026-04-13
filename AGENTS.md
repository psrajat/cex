# cex - Code EXplainer

## Project Stack
- **Language:** Python 3.12+
- **Environment:** Managed via [uv](https://github.com)
- **Framework:** [Psycopg2](https://pypi.org/project/psycopg2/) for DB access
- **Testing:** [pytest](https://pytest.org) with `pytest-asyncio`

## Critical Commands
- **Install Dependencies:** `uv sync`
- **Run Tests:** `uv run pytest`
- **Linting:** `uv run ruff check .`
- **Type Checking:** `uv run pyright`

## Python Best Practices
- Use **Type Hints** for all function signatures (PEP 484).
- Prefer **f-strings** over `.format()` or `%`.
- Use **async/await** for all I/O bound operations.
- Catch specific exceptions; never use a bare `except: Exception`.

## Testing Guidelines
- Write all tests in the `tests/` directory following the `test_*.py` pattern.
- Every new feature must include a corresponding unit test.
- Use `unittest.mock` for any network-dependent services.

## Boundaries & Constraints
- **Never** modify files in the `scripts/legacy/` folder.
- **Do not** add new dependencies without explicit permission.
- **Never** include secrets or hardcoded API keys in any generated code.
