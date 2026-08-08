# portfolio-market-data

## End-user installation

The dashboard and data workspace install the immutable `v0.2.0` package from GitHub. A source
checkout is not required. To install the CLI by itself:

```powershell
uv tool install "portfolio-market-data @ git+https://github.com/T1m-V/portfolio-market-data.git@v0.2.0"
portfolio-market --help
```

## Developer setup

Clone `portfolio-core` next to this repository. `[tool.uv.sources]` then overrides the released
core dependency with `../portfolio-core` in editable mode:

```powershell
cd C:\Users\timvo\source\portfolio\portfolio-market-data
uv sync --frozen
uv run python -c "from pathlib import Path; import portfolio_core; print(Path(portfolio_core.__file__).resolve())"
uv run ruff check src tests
uv run python -m pytest
uv build
```

The printed core path should be inside the sibling `portfolio-core` checkout. Python edits there
are visible immediately; rerun `uv lock` and `uv sync` only after dependency metadata changes.

Loader commands operate on an explicit data workspace:

```powershell
uv run portfolio-market --data-dir C:\path\to\portfolio-data prices update
uv run portfolio-market --data-dir C:\path\to\portfolio-data transactions update
```

These update commands call external services and mutate data; they are not ordinary test commands.
