from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from portfolio_core import atomic_write_csv, get_forex_rate


@dataclass
class AssetPosition:
    """Tracks the running state and calculations of a single ISIN."""

    isin: str
    quantity: float = 0.0
    principal: float = 0.0
    fees: float = 0.0
    taxes: float = 0.0
    dividends: float = 0.0
    currency: str = "EUR"
    prices_folder: Path | None = None

    def convert_to_eur(self, amount: float, date: str) -> float:
        if self.currency == "EUR":
            return amount
        if self.prices_folder is None:
            raise RuntimeError("prices_folder is required for non-EUR assets")
        rate = get_forex_rate(
            currency=self.currency,
            date=date,
            prices_folder=self.prices_folder,
        )
        return amount * rate

    def buy(self, qty: float, price: float, fees: float, taxes: float, date: str):
        self.quantity += qty
        self.principal += self.convert_to_eur(amount=qty * price, date=date)
        self.fees += fees
        self.taxes += taxes

    def sell(self, qty: float, price: float, fees: float, taxes: float, date: str):
        self.quantity -= qty
        self.principal -= self.convert_to_eur(amount=qty * price, date=date)
        self.fees += fees
        self.taxes += taxes

    def split(self, ratio: float):
        self.quantity *= ratio

    def dividend(self, amount: float, taxes: float, date: str):
        self.dividends += self.convert_to_eur(amount=amount, date=date)
        self.taxes += taxes

    def to_snapshot(self, date) -> dict:
        return {
            "Date": date,
            "ISIN": self.isin,
            "Quantity": round(self.quantity, 6),
            "Principal Invested": round(self.principal, 2),
            "Cumulative Fees": round(self.fees, 2),
            "Cumulative Taxes": round(self.taxes, 2),
            "Gross Dividends": round(self.dividends, 2),
        }


class PortfolioTracker:
    def __init__(self, *, stock_metadata: dict[str, dict[str, Any]], prices_folder: Path):
        self.stock_metadata = stock_metadata
        self.prices_folder = prices_folder
        self.assets: dict[str, AssetPosition] = {}
        self.history: list[dict] = []

    def fetch_asset(self, isin: str) -> AssetPosition:
        if isin not in self.assets:
            currency = self.stock_metadata.get(isin, {}).get("currency", "EUR")
            self.assets[isin] = AssetPosition(
                isin=isin,
                currency=currency,
                prices_folder=self.prices_folder,
            )
        return self.assets[isin]

    def process_transaction(self, row: pd.Series):
        isin = row["ISIN"]
        tx_type = row["Type"]
        val = row["Quantity"]
        price = row["Price"]
        fees = row.get("Fees", 0) or 0
        taxes = row.get("Taxes", 0) or 0
        date = row["Date"]

        asset = self.fetch_asset(isin)

        if tx_type == "BUYING":
            asset.buy(qty=val, price=price, fees=fees, taxes=taxes, date=date)

        elif tx_type == "SELLING":
            asset.sell(qty=val, price=price, fees=fees, taxes=taxes, date=date)

        elif tx_type == "STOCK_SPLIT":
            asset.split(ratio=val)
            for record in self.history:
                if record["ISIN"] == isin:
                    record["Quantity"] *= val

        elif tx_type == "DIVIDEND":
            asset.dividend(amount=val * price, taxes=taxes, date=date)

        new_snapshot = asset.to_snapshot(date)
        if (
            (self.history)
            and (self.history[-1]["ISIN"] == isin)
            and (self.history[-1]["Date"] == date)
        ):
            self.history[-1] = new_snapshot
        else:
            # First transaction of the day for this asset, so append
            self.history.append(new_snapshot)

    def save_to_csv(self, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(self.history)
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        atomic_write_csv(frame=df, path=output_path)
        print(f"🚀 Portfolio snapshots successfully saved to {output_path}")


def generate_portfolio_snapshots(
    *,
    input_csv: Path,
    output_csv: Path,
    stock_metadata: dict[str, dict[str, Any]],
    prices_folder: Path,
) -> None:
    df = pd.read_csv(input_csv)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values(by=["Date", "ISIN"], ascending=[True, True])

    tracker = PortfolioTracker(stock_metadata=stock_metadata, prices_folder=prices_folder)
    for _, row in df.iterrows():
        tracker.process_transaction(row)

    tracker.save_to_csv(output_csv)
