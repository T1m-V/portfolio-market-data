from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import pandas as pd
import requests
from portfolio_core import PortfolioContext, atomic_write_csv, atomic_write_json, get_forex_rate

DEFAULT_TRANSACTION_LIMIT = 20
GETQUIN_URL = "https://api-gql-v2.getquin.com/"
TRANSACTION_COLUMNS = [
    "Transaction ID",
    "Date",
    "Type",
    "Asset Name",
    "ISIN",
    "Quantity",
    "Price",
    "Currency",
    "Fees",
    "Taxes",
]
SNAPSHOT_COLUMNS = [
    "Date",
    "ISIN",
    "Quantity",
    "Principal Invested",
    "Cumulative Fees",
    "Cumulative Taxes",
    "Gross Dividends",
]


def _request(*, token: str, operation: str, variables: dict, query_file: str) -> dict:
    query = files("portfolio_market_data.resources").joinpath(f"queries/{query_file}")
    response = requests.post(
        GETQUIN_URL,
        headers={
            "authorization": token,
            "content-type": "application/json",
            "apollographql-client-name": "web",
            "apollographql-client-version": "2.213.2",
        },
        json={
            "operationName": operation,
            "variables": variables,
            "query": query.read_text(encoding="utf-8"),
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if errors := data.get("errors"):
        messages = ", ".join(error.get("message", "Unknown error") for error in errors)
        raise RuntimeError(f"getquin API returned GraphQL errors: {messages}")
    return data


def _download_transactions(*, output_file: Path, token: str, limit: int) -> list[dict]:
    data = _request(
        token=token,
        operation="getDashboardAggregatedTransactions",
        variables={
            "isin__in": [],
            "limit": limit,
            "offset": 0,
            "transaction_type__in": [],
        },
        query_file="transactions.txt",
    )
    transactions = data.get("data", {}).get("transactions", {}).get("results")
    if not isinstance(transactions, list):
        raise RuntimeError("getquin API response did not include transaction results")
    atomic_write_json(data=data, path=output_file)
    return transactions


def _download_splits(
    *, transactions: list[dict], output_file: Path, token: str
) -> list[dict]:
    dates = [pd.Timestamp(transaction["timestamp"]) for transaction in transactions]
    data = _request(
        token=token,
        operation="getSplits",
        variables={
            "include_future": True,
            "isin__in": sorted({transaction["isin"] for transaction in transactions}),
            "start_date_from": min(dates).strftime("%Y-%m-%d"),
            "start_date_to": max(dates).strftime("%Y-%m-%d"),
        },
        query_file="stock_split.txt",
    )
    splits = data.get("data", {}).get("splits")
    if not isinstance(splits, list):
        raise RuntimeError("getquin API response did not include stock splits")
    atomic_write_json(data=data, path=output_file)
    return splits


def _normalize_transactions(
    *, transactions: list[dict], splits: list[dict], output_file: Path
) -> pd.DataFrame:
    names = {transaction["isin"]: transaction["instrument"]["name"] for transaction in transactions}
    rows = [
        {
            "Transaction ID": transaction["id"],
            "Date": transaction["timestamp"],
            "Type": transaction["transaction_type"],
            "Asset Name": transaction["instrument"]["name"],
            "ISIN": transaction["isin"],
            "Quantity": transaction["units"],
            "Price": transaction["price"],
            "Currency": transaction["price_currency"],
            "Fees": transaction["costs"],
            "Taxes": transaction["taxes"],
        }
        for transaction in transactions
    ]
    rows.extend(
        {
            "Transaction ID": (
                f"split_{split['isin']}_{split['start_date']}_"
                f"{split['numerator']}_{split['denominator']}"
            ),
            "Date": split["start_date"],
            "Type": "STOCK_SPLIT",
            "Asset Name": names.get(split["isin"], split["isin"]),
            "ISIN": split["isin"],
            "Quantity": split["numerator"] / split["denominator"],
            "Price": 0,
            "Currency": "",
            "Fees": 0,
            "Taxes": 0,
        }
        for split in splits
    )

    incoming = pd.DataFrame(rows, columns=TRANSACTION_COLUMNS)
    if output_file.exists():
        incoming = pd.concat([pd.read_csv(output_file), incoming], ignore_index=True)
    incoming = incoming.drop_duplicates(subset="Transaction ID", keep="last")
    incoming["Date"] = pd.to_datetime(incoming["Date"], format="ISO8601", utc=True).dt.tz_localize(
        None
    )
    incoming = incoming.sort_values("Date", ascending=False)
    incoming["Date"] = incoming["Date"].dt.strftime("%Y-%m-%d")
    incoming = incoming[TRANSACTION_COLUMNS].reset_index(drop=True)
    atomic_write_csv(frame=incoming, path=output_file)
    return incoming


@dataclass(slots=True)
class _Position:
    quantity: float = 0.0
    principal: float = 0.0
    fees: float = 0.0
    taxes: float = 0.0
    dividends: float = 0.0


def _generate_snapshots(
    *, transactions: pd.DataFrame, output_file: Path, prices_folder: Path
) -> pd.DataFrame:
    ordered = transactions.copy()
    ordered["Date"] = pd.to_datetime(ordered["Date"])
    ordered = ordered.sort_values(["Date", "ISIN"])
    positions: dict[str, _Position] = {}
    history: list[dict] = []

    for row in ordered.to_dict("records"):
        isin = row["ISIN"]
        position = positions.setdefault(isin, _Position())
        quantity = float(row["Quantity"])
        price = float(row["Price"])
        date = row["Date"]

        match row["Type"]:
            case "BUYING" | "SELLING" as transaction_type:
                direction = 1 if transaction_type == "BUYING" else -1
                position.quantity += direction * quantity
                position.principal += direction * quantity * price * get_forex_rate(
                    currency=row["Currency"],
                    date=date,
                    prices_folder=prices_folder,
                )
                position.fees += float(row["Fees"])
                position.taxes += float(row["Taxes"])
            case "DIVIDEND":
                position.dividends += quantity * price * get_forex_rate(
                    currency=row["Currency"],
                    date=date,
                    prices_folder=prices_folder,
                )
                position.taxes += float(row["Taxes"])
            case "STOCK_SPLIT":
                position.quantity *= quantity
                for snapshot in history:
                    if snapshot["ISIN"] == isin:
                        snapshot["Quantity"] *= quantity
            case unexpected:
                raise ValueError(f"Unsupported transaction type: {unexpected}")

        snapshot = {
            "Date": date,
            "ISIN": isin,
            "Quantity": round(position.quantity, 6),
            "Principal Invested": round(position.principal, 2),
            "Cumulative Fees": round(position.fees, 2),
            "Cumulative Taxes": round(position.taxes, 2),
            "Gross Dividends": round(position.dividends, 2),
        }
        if history and history[-1]["Date"] == date and history[-1]["ISIN"] == isin:
            history[-1] = snapshot
        else:
            history.append(snapshot)

    frame = pd.DataFrame(history, columns=SNAPSHOT_COLUMNS)
    frame["Date"] = pd.to_datetime(frame["Date"]).dt.strftime("%Y-%m-%d")
    atomic_write_csv(frame=frame, path=output_file)
    return frame


def update_transactions(
    *, context: PortfolioContext, transaction_limit: int = DEFAULT_TRANSACTION_LIMIT
) -> None:
    """Refresh Getquin exports, normalized transactions, and portfolio snapshots."""
    print("Starting market transaction update...")
    paths = context.paths
    token = context.getquin_token()
    transactions = _download_transactions(
        output_file=paths.transaction_export,
        token=token,
        limit=transaction_limit,
    )
    splits = _download_splits(
        transactions=transactions,
        output_file=paths.stock_split_export,
        token=token,
    )
    normalized = _normalize_transactions(
        transactions=transactions,
        splits=splits,
        output_file=paths.normalized_transactions,
    )
    _generate_snapshots(
        transactions=normalized,
        output_file=paths.portfolio_snapshot,
        prices_folder=paths.prices,
    )
    print("Market transaction update finished successfully.")
