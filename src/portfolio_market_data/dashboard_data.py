from __future__ import annotations

import pandas as pd
from portfolio_core import PortfolioContext

COLS_TO_FILL = [
    "Quantity",
    "Principal Invested",
    "Cumulative Fees",
    "Cumulative Taxes",
    "Gross Dividends",
]


def _process_price_history(
    *,
    frame: pd.DataFrame,
    isin: str,
    end_date: pd.Timestamp,
    context: PortfolioContext,
) -> pd.DataFrame:
    prices = frame.copy()
    prices["Date"] = pd.to_datetime(prices["Date"])
    prices = prices[prices["Date"] <= end_date]
    if prices.empty:
        return pd.DataFrame()

    prices = prices.set_index("Date")
    full_range = pd.date_range(start=prices.index.min(), end=end_date, freq="D")
    currency = context.stock_metadata().get(isin, {}).get("currency", "EUR")
    if currency != "EUR":
        fx_path = context.paths.direct_price(f"{currency}_EUR")
        if not fx_path.exists():
            raise FileNotFoundError(f"No forex data for {currency}: {fx_path}")
        forex = pd.read_csv(fx_path)
        forex["Date"] = pd.to_datetime(forex["Date"])
        forex = forex.rename(columns={"Price": "FX_Rate"})
        prices = pd.merge(prices, forex[["Date", "FX_Rate"]], on="Date", how="left")
        prices["Price"] = prices["Price"] * prices["FX_Rate"]
        prices = prices.drop(columns=["FX_Rate"]).set_index("Date")

    prices = prices.reindex(full_range).ffill().reset_index()
    prices = prices.rename(columns={"index": "Date"})
    prices["ISIN"] = isin
    return prices[["Date", "ISIN", "Price"]]


def _finalize_calculations(
    *,
    frame: pd.DataFrame,
    context: PortfolioContext,
) -> pd.DataFrame:
    name_lookup = {
        isin: info["name"] for isin, info in context.stock_metadata().items()
    }
    frame["Asset Name"] = frame["ISIN"].map(name_lookup).fillna(frame["ISIN"])
    frame["Market Value"] = frame["Quantity"] * frame["Price"]
    return frame


def load_stock_history(
    *,
    context: PortfolioContext,
    end_date: str,
    isins: list[str] | None = None,
) -> pd.DataFrame:
    """Load dashboard-ready daily stock positions and valuations."""
    end = pd.to_datetime(end_date)
    if isins:
        price_files = [context.paths.direct_price(isin) for isin in isins]
        missing = [path.stem for path in price_files if not path.exists()]
        if missing:
            raise FileNotFoundError(f"Price files not found: {', '.join(missing)}")
    else:
        price_files = list(context.paths.prices.glob("*.csv"))

    price_frames = []
    for file_path in price_files:
        processed = _process_price_history(
            frame=pd.read_csv(file_path),
            isin=file_path.stem,
            end_date=end,
            context=context,
        )
        if not processed.empty:
            price_frames.append(processed)
    if not price_frames:
        return pd.DataFrame()

    prices = pd.concat(price_frames, ignore_index=True)
    portfolio = pd.read_csv(context.paths.portfolio_snapshot)
    portfolio["Date"] = pd.to_datetime(portfolio["Date"])
    portfolio = portfolio[portfolio["Date"] <= end]
    if isins:
        portfolio = portfolio[portfolio["ISIN"].isin(isins)]

    merged = pd.merge(prices, portfolio, on=["Date", "ISIN"], how="left")
    merged = merged.sort_values(["ISIN", "Date"])
    merged[COLS_TO_FILL] = merged.groupby("ISIN")[COLS_TO_FILL].ffill().fillna(0)
    return _finalize_calculations(frame=merged, context=context)


def load_recent_stock_transactions(
    *,
    context: PortfolioContext,
    end_date: str,
    isins: list[str] | None = None,
    limit: int | None = 5,
) -> pd.DataFrame:
    frame = pd.read_csv(context.paths.normalized_transactions)
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"])
    frame = frame[frame["Date"] <= pd.to_datetime(end_date)]
    if isins:
        frame = frame[frame["ISIN"].isin(isins)]
    frame = frame.sort_values("Date", ascending=False).copy()
    if limit is not None:
        frame = frame.head(limit)
    frame["Date"] = frame["Date"].dt.strftime("%Y-%m-%d")
    return frame


def get_stock_start_date(
    *, context: PortfolioContext, isins: list[str] | None = None
) -> str | None:
    if isins == [] or not context.paths.normalized_transactions.exists():
        return None
    frame = pd.read_csv(context.paths.normalized_transactions, usecols=["Date", "ISIN"])
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"])
    if isins:
        frame = frame[frame["ISIN"].isin(isins)]
    if frame.empty:
        return None
    return frame["Date"].min().strftime("%Y-%m-%d")
