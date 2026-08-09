from __future__ import annotations

import pandas as pd
from portfolio_core import PortfolioContext

POSITION_COLUMNS = [
    "Quantity",
    "Principal Invested",
    "Cumulative Fees",
    "Cumulative Taxes",
    "Gross Dividends",
]


def _daily_prices(
    *, context: PortfolioContext, isin: str, currency: str, end: pd.Timestamp
) -> pd.DataFrame:
    prices = pd.read_csv(context.paths.direct_price(isin))
    prices["Date"] = pd.to_datetime(prices["Date"])
    prices = prices[prices["Date"] <= end].sort_values("Date")
    if prices.empty:
        return pd.DataFrame(columns=["Date", "ISIN", "Price"])

    if currency != "EUR":
        forex = pd.read_csv(context.paths.direct_price(f"{currency}_EUR"))
        forex["Date"] = pd.to_datetime(forex["Date"])
        forex = forex.rename(columns={"Price": "FX Rate"}).sort_values("Date")
        prices = pd.merge_asof(prices, forex[["Date", "FX Rate"]], on="Date")
        prices["Price"] *= prices.pop("FX Rate")

    dates = pd.date_range(prices["Date"].min(), end, freq="D")
    prices = prices.set_index("Date").reindex(dates).ffill().rename_axis("Date").reset_index()
    prices["ISIN"] = isin
    return prices[["Date", "ISIN", "Price"]]


def load_stock_history(
    *, context: PortfolioContext, end_date: str, isins: list[str] | None = None
) -> pd.DataFrame:
    """Load dashboard-ready daily stock positions and EUR valuations."""
    metadata = context.stock_metadata()
    identifiers = list(metadata) if isins is None else isins
    missing = [isin for isin in identifiers if not context.paths.direct_price(isin).exists()]
    if missing:
        raise FileNotFoundError(f"Price files not found: {', '.join(missing)}")

    end = pd.Timestamp(end_date)
    price_frames = []
    for isin in identifiers:
        frame = _daily_prices(
            context=context,
            isin=isin,
            currency=metadata[isin]["currency"],
            end=end,
        )
        if not frame.empty:
            price_frames.append(frame)
    if not price_frames:
        return pd.DataFrame()

    portfolio = pd.read_csv(context.paths.portfolio_snapshot)
    portfolio["Date"] = pd.to_datetime(portfolio["Date"])
    portfolio = portfolio[
        (portfolio["Date"] <= end) & portfolio["ISIN"].isin(identifiers)
    ]

    frame = pd.merge(
        pd.concat(price_frames, ignore_index=True),
        portfolio,
        on=["Date", "ISIN"],
        how="left",
    ).sort_values(["ISIN", "Date"])
    frame[POSITION_COLUMNS] = frame.groupby("ISIN")[POSITION_COLUMNS].ffill().fillna(0)
    frame["Asset Name"] = frame["ISIN"].map(
        {isin: details["name"] for isin, details in metadata.items()}
    )
    frame["Market Value"] = frame["Quantity"] * frame["Price"]
    return frame


def load_recent_stock_transactions(
    *,
    context: PortfolioContext,
    end_date: str,
    isins: list[str] | None = None,
    limit: int = 5,
) -> pd.DataFrame:
    frame = pd.read_csv(context.paths.normalized_transactions)
    frame["Date"] = pd.to_datetime(frame["Date"])
    frame = frame[frame["Date"] <= pd.Timestamp(end_date)]
    if isins is not None:
        frame = frame[frame["ISIN"].isin(isins)]
    frame = frame.sort_values("Date", ascending=False).head(limit).copy()
    frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d")
    return frame


def get_stock_start_date(
    *, context: PortfolioContext, isins: list[str] | None = None
) -> str | None:
    if not context.paths.normalized_transactions.exists():
        return None
    frame = pd.read_csv(context.paths.normalized_transactions, usecols=["Date", "ISIN"])
    if isins is not None:
        frame = frame[frame["ISIN"].isin(isins)]
    if frame.empty:
        return None
    return pd.to_datetime(frame["Date"]).min().strftime("%Y-%m-%d")
