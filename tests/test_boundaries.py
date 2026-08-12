import json
from pathlib import Path

import pandas as pd
import pytest
from portfolio_core import PortfolioContext

from portfolio_market_data import cli, prices, transactions
from portfolio_market_data.dashboard_data import (
    get_stock_start_date,
    load_recent_stock_transactions,
    load_stock_history,
)


def test_dashboard_stock_projections_use_metadata_assets_and_asof_forex(tmp_path: Path) -> None:
    context = PortfolioContext.from_root(tmp_path, load_secrets=False)
    context.paths.config.mkdir(parents=True)
    context.paths.prices.mkdir()
    context.paths.transactions.mkdir()
    context.paths.stock_metadata.write_text(
        json.dumps(
            {
                "EUR_ASSET": {"name": "Euro Asset", "currency": "EUR"},
                "USD_ASSET": {"name": "US Asset", "currency": "USD"},
            }
        ),
        encoding="utf-8",
    )
    for symbol, values in {
        "EUR_ASSET": [("2026-01-02", 11), ("2026-01-01", 10)],
        "USD_ASSET": [("2026-01-02", 22), ("2026-01-01", 20)],
        "USD_EUR": [("2026-01-02", 0.6), ("2025-12-31", 0.5)],
    }.items():
        pd.DataFrame(values, columns=["Date", "Price"]).to_csv(
            context.paths.direct_price(symbol), index=False
        )
    pd.DataFrame(
        [
            ["2026-01-01", "EUR_ASSET", 2, 20, 0, 0, 0],
            ["2026-01-02", "USD_ASSET", 3, 30, 0, 0, 0],
        ],
        columns=[
            "Date",
            "ISIN",
            "Quantity",
            "Principal Invested",
            "Cumulative Fees",
            "Cumulative Taxes",
            "Gross Dividends",
        ],
    ).to_csv(context.paths.portfolio_snapshot, index=False)
    pd.DataFrame(
        [
            ["one", "2026-01-01", "BUYING", "Euro Asset", "EUR_ASSET", 2, 10, "EUR", 0, 0],
            ["two", "2026-01-02", "BUYING", "US Asset", "USD_ASSET", 3, 10, "USD", 0, 0],
        ],
        columns=transactions.TRANSACTION_COLUMNS,
    ).to_csv(context.paths.normalized_transactions, index=False)

    history = load_stock_history(context=context, end_date="2026-01-03")

    assert set(history["ISIN"]) == {"EUR_ASSET", "USD_ASSET"}
    latest = history.groupby("ISIN").tail(1).set_index("ISIN")
    assert latest.loc["EUR_ASSET", "Market Value"] == 22
    assert latest.loc["USD_ASSET", "Market Value"] == pytest.approx(39.6)
    assert load_recent_stock_transactions(
        context=context, end_date="2026-01-03", isins=[], limit=5
    ).empty
    assert get_stock_start_date(context=context, isins=["USD_ASSET"]) == "2026-01-02"


def test_cli_preserves_both_cross_repository_commands(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "portfolio.toml").write_text("schema_version = 1\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(prices, "update_prices", lambda *, context: calls.append("prices") or 0)
    monkeypatch.setattr(
        transactions,
        "update_transactions",
        lambda *, context, transaction_limit: calls.append(("transactions", transaction_limit)),
    )

    assert cli.main(["--data-dir", str(tmp_path), "prices", "update"]) == 0
    assert (
        cli.main(
            ["--data-dir", str(tmp_path), "transactions", "update", "--limit", "7"]
        )
        == 0
    )
    assert calls == ["prices", ("transactions", 7)]
