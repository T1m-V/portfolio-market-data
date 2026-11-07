import json
from pathlib import Path

import pandas as pd
from portfolio_core import PortfolioContext

from portfolio_market_data import prices


def test_price_update_uses_waterfall_and_rebuilds_latest_summary(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    config = tmp_path / "config"
    prices_dir = tmp_path / "prices"
    config.mkdir()
    prices_dir.mkdir()
    (config / "stock_metadata.json").write_text(
        json.dumps(
            {
                "ACTIVE": {
                    "ticker": "ACTIVE",
                    "waterfall": ["Yahoo"],
                    "history_start": "2026-01-02",
                },
                "INACTIVE": {"active": False, "waterfall": ["Yahoo"]},
            }
        ),
        encoding="utf-8",
    )
    (config / "currency_metadata.json").write_text("{}", encoding="utf-8")
    pd.DataFrame({"Date": ["2026-01-01"], "Price": [1]}).to_csv(
        prices_dir / "ACTIVE.csv", index=False
    )
    pd.DataFrame({"Date": ["2025-01-01"], "Price": [2]}).to_csv(
        prices_dir / "INACTIVE.csv", index=False
    )
    monkeypatch.setitem(
        prices.FETCHERS,
        "Yahoo",
        lambda identifier, metadata, days: pd.DataFrame(
            {"Date": ["2026-01-03"], "Price": [3]}
        ),
    )

    context = PortfolioContext.load(tmp_path, load_secrets=False)
    assert prices.update_prices(context=context) == 0

    assert pd.read_csv(prices_dir / "ACTIVE.csv").to_dict("records") == [
        {"Date": "2026-01-03", "Price": 3}
    ]
    latest = pd.read_csv(tmp_path / "latest_prices.csv")
    assert latest[["isin", "price"]].to_dict("records") == [
        {"isin": "ACTIVE", "price": 3},
        {"isin": "INACTIVE", "price": 2},
    ]
    assert "INACTIVE] skipped: inactive" in capsys.readouterr().out
