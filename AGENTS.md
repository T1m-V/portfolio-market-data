# AGENTS.md

## Purpose

`portfolio-market-data` owns off-chain data acquisition and transformation: historical market
prices, latest-price rebuilding, Getquin exports, stock splits, transaction normalization, and
portfolio snapshots. It is an installable library and exposes the `portfolio-market` CLI.

## Repository Role

| Repository | Relationship to this package |
| --- | --- |
| `portfolio-core` | The only first-party dependency. It owns paths, settings, metadata, forex lookup, and canonical price utilities. |
| `portfolio-dashboard` | Installs this package and invokes its CLI in background refresh jobs. It should not duplicate loader logic. |
| `portfolio-data` | Runtime workspace and automation host. Its scheduled workflow runs the price CLI and its lockfile pins this package. |
| `portfolio-crypto-data` | Sibling loader. There must be no direct dependency in either direction; shared behavior belongs in core. |

## Package Map

- `portfolio_market_data.prices`: Yahoo, Morningstar, DefiLlama, merge, and latest-price flows.
- `portfolio_market_data.transactions`: Getquin export, stock splits, normalization, and snapshots.
- `portfolio_market_data.dashboard_data`: read-only stock projections deliberately consumed by the
  dashboard.
- `portfolio_market_data.resources.queries`: packaged Getquin query text; load it with
  `importlib.resources` so wheels work without a checkout.
- `portfolio_market_data.cli`: stable process boundary used by people, the dashboard, and GitHub
  Actions.

Supported commands:

```powershell
uv run portfolio-market --data-dir C:\path\to\portfolio-data prices update
uv run portfolio-market --data-dir C:\path\to\portfolio-data transactions update
```

## Refactoring Policy

- Optimize for maintainability, not compatibility with the former monorepo.
- Change internal modules, signatures, and call patterns freely; update tests and all consumers in
  the same change.
- Do not recreate `price_history`, `historical_transactions`, or `file_paths` compatibility
  namespaces.
- Do not keep deprecated CLI spellings or duplicate old/new functions unless explicitly requested.
- Use `portfolio-core` as the sole owner of shared paths and canonical price behavior.
- If the dashboard needs a new refresh operation, expose it deliberately through this CLI instead
  of importing and orchestrating private loader functions.
- Prefer replacing a data contract with a coordinated schema migration over silently supporting
  multiple formats.

The CLI and persisted files are cross-repository contracts, not permanent legacy APIs. Breaking
them is acceptable when `portfolio-dashboard`, `portfolio-data`, documentation, tests, and release
tags are updated together.

## Data Contracts

- `prices/*.csv`: exactly `Date`, `Price`, sorted descending by `Date`.
- `latest_prices.csv`: `date, isin, price`, rebuilt from the newest row of each direct price file.
- Getquin exports and normalized snapshots live below `transactions/` in the external workspace.
- Stock and currency metadata come from `config/` through `portfolio-core`.
- Query files must be present in built wheels.

Avoid unnecessary rewrites of unchanged CSVs. Do not edit private transaction output by hand when
the loader or a focused migration can produce it.

## External Effects

Price and transaction commands call external services and write user data. Do not run them during
ordinary linting, tests, review, or refactoring unless the user explicitly requests a refresh.
Tests must mock network boundaries and use temporary workspaces.

`GETQUIN_TOKEN` is loaded from the selected workspace `.env` or the process environment. Credential
files are not supported. Never print, commit, or copy the token into fixtures.

Both CLI commands acquire the core-owned workspace mutation lock and publish a run manifest.
Writers must use core atomic-write helpers so dashboard readers never observe half-written files.

## Release Coordination

- A core upgrade requires a new core tag, an updated `portfolio-core` requirement/source, and a
  regenerated lockfile here.
- A market-data release requires a new tag followed by source/lock updates in
  `portfolio-dashboard` and `portfolio-data`.
- Never move a published tag; publish a new package version.

## Development

```powershell
uv sync
uv run ruff check src tests
uv run python -m pytest
uv build
```

After building, verify that both query `.txt` resources are in the wheel. The actual virtual
environment belongs in uv's centralized cache, not in OneDrive or Git.
