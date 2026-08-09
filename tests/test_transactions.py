import json
from pathlib import Path

import pandas as pd
import pytest
from portfolio_core import PortfolioContext

from portfolio_market_data import transactions


def _transaction(
    transaction_id: str,
    date: str,
    transaction_type: str,
    *,
    quantity: float,
    price: float,
) -> dict:
    return {
        "id": transaction_id,
        "timestamp": f"{date}T10:00:00Z",
        "transaction_type": transaction_type,
        "isin": "USD_ASSET",
        "instrument": {"name": "US Asset"},
        "units": quantity,
        "price": price,
        "price_currency": "USD",
        "costs": 1 if transaction_type == "BUYING" else 0,
        "taxes": 0,
    }


class _Response:
    def __init__(self, data: dict) -> None:
        self.data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self.data


def test_transaction_update_writes_all_workspace_contracts(monkeypatch, tmp_path: Path) -> None:
    context = PortfolioContext.from_root(tmp_path, load_secrets=False)
    context.paths.prices.mkdir(parents=True)
    pd.DataFrame({"Date": ["2025-12-31"], "Price": [0.9]}).to_csv(
        context.paths.direct_price("USD_EUR"), index=False
    )
    fetched = [
        _transaction("buy", "2026-01-01", "BUYING", quantity=2, price=10),
        _transaction("dividend", "2026-01-03", "DIVIDEND", quantity=4, price=1),
        _transaction("sell", "2026-01-04", "SELLING", quantity=1, price=12),
    ]
    split = {
        "isin": "USD_ASSET",
        "start_date": "2026-01-02",
        "numerator": 2,
        "denominator": 1,
    }
    payloads = []

    def post(url, **kwargs):
        payloads.append(kwargs["json"])
        if kwargs["json"]["operationName"] == "getSplits":
            return _Response({"data": {"splits": [split]}})
        return _Response({"data": {"transactions": {"results": fetched}}})

    monkeypatch.setattr(transactions.requests, "post", post)
    monkeypatch.setattr(context.__class__, "getquin_token", lambda self: "token")

    transactions.update_transactions(context=context, transaction_limit=7)

    assert payloads[0]["variables"]["limit"] == 7
    assert json.loads(context.paths.transaction_export.read_text())["data"]["transactions"][
        "results"
    ] == fetched
    normalized = pd.read_csv(context.paths.normalized_transactions)
    assert normalized.columns.tolist() == transactions.TRANSACTION_COLUMNS
    assert normalized["Transaction ID"].tolist() == [
        "sell",
        "dividend",
        "split_USD_ASSET_2026-01-02_2_1",
        "buy",
    ]

    snapshots = pd.read_csv(context.paths.portfolio_snapshot)
    assert snapshots.columns.tolist() == transactions.SNAPSHOT_COLUMNS
    assert snapshots[["Quantity", "Principal Invested", "Gross Dividends"]].to_dict(
        "records"
    ) == [
        {"Quantity": 4.0, "Principal Invested": 18.0, "Gross Dividends": 0.0},
        {"Quantity": 4.0, "Principal Invested": 18.0, "Gross Dividends": 0.0},
        {"Quantity": 4.0, "Principal Invested": 18.0, "Gross Dividends": 3.6},
        {"Quantity": 3.0, "Principal Invested": 7.2, "Gross Dividends": 3.6},
    ]


def test_normalization_keeps_history_and_replaces_refetched_ids(tmp_path: Path) -> None:
    output = tmp_path / "getquin.csv"
    old = _transaction("old", "2025-01-01", "BUYING", quantity=1, price=1)
    overlap = _transaction("same", "2026-01-01", "BUYING", quantity=1, price=1)
    transactions._normalize_transactions(
        transactions=[old, overlap], splits=[], output_file=output
    )
    overlap["price"] = 2

    result = transactions._normalize_transactions(
        transactions=[overlap], splits=[], output_file=output
    )

    assert result["Transaction ID"].tolist() == ["same", "old"]
    assert result.loc[result["Transaction ID"] == "same", "Price"].item() == 2


def test_graphql_errors_do_not_replace_export(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "transactions.json"
    monkeypatch.setattr(
        transactions.requests,
        "post",
        lambda *args, **kwargs: _Response({"errors": [{"message": "unauthorized"}]}),
    )

    with pytest.raises(RuntimeError, match="unauthorized"):
        transactions._download_transactions(output_file=output, token="bad", limit=20)
    assert not output.exists()
