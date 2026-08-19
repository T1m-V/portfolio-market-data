from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import mstarpy
import pandas as pd
import requests
import yfinance as yf
from portfolio_core import (
    PRICE_COLUMNS,
    PortfolioContext,
    atomic_write_csv,
    load_price_csv,
    merge_price_frames,
    normalize_price_frame,
    save_price_csv,
)

HISTORY_DAYS = 10
FT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _empty_prices() -> pd.DataFrame:
    return pd.DataFrame(columns=PRICE_COLUMNS)


def _first_ft_date(value: object) -> str:
    match = re.search(r".*?\d{4}", str(value))
    return match.group() if match else str(value)


def _fetch_yahoo(identifier: str, config: dict[str, Any], days: int) -> pd.DataFrame:
    ticker = yf.Ticker(config["ticker"])
    end = datetime.now()
    history = ticker.history(
        start=(end - timedelta(days=days)).strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=False,
    )
    if history.empty:
        return _empty_prices()

    frame = history[["Close"]].reset_index().rename(columns={"Close": "Price"})
    frame["Date"] = pd.to_datetime(frame["Date"]).dt.tz_localize(None)
    return frame[PRICE_COLUMNS]


def _fetch_morningstar(identifier: str, config: dict[str, Any], days: int) -> pd.DataFrame:
    end = datetime.now()
    history = mstarpy.Funds(term=identifier).nav(
        start_date=end - timedelta(days=days),
        end_date=end,
    )
    if not history:
        return _empty_prices()
    return pd.DataFrame(history).rename(columns={"date": "Date", "nav": "Price"})[
        PRICE_COLUMNS
    ]


def _fetch_ft(identifier: str, config: dict[str, Any], days: int) -> pd.DataFrame:
    symbol = config.get("ft_symbol", f"{identifier}:EUR")
    asset_type = config.get("ft_asset_type", "funds")
    response = requests.get(
        f"https://markets.ft.com/data/{asset_type}/tearsheet/historical?s={symbol}",
        headers={"User-Agent": FT_USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()

    frame = pd.read_html(StringIO(response.text))[0]
    frame["Date"] = frame["Date"].map(_first_ft_date)
    frame["Price"] = frame["Close"].replace({",": ""}, regex=True)
    return frame[PRICE_COLUMNS]


def _fetch_llama(identifier: str, config: dict[str, Any], days: int) -> pd.DataFrame:
    ticker = config["ticker"]
    end = datetime.now()
    rows = []
    for offset in range(days):
        target = end - timedelta(days=offset)
        response = requests.get(
            f"https://coins.llama.fi/prices/historical/{int(target.timestamp())}/{ticker}",
            timeout=20,
        )
        response.raise_for_status()
        price = response.json().get("coins", {}).get(ticker, {}).get("price")
        if price is not None:
            rows.append({"Date": target.date(), "Price": price})
        if offset + 1 < days:
            time.sleep(0.15)
    return pd.DataFrame(rows, columns=PRICE_COLUMNS)


PriceFetcher = Callable[[str, dict[str, Any], int], pd.DataFrame]
FETCHERS: dict[str, PriceFetcher] = {
    "Yahoo": _fetch_yahoo,
    "Morningstar": _fetch_morningstar,
    "FT": _fetch_ft,
    "Llama": _fetch_llama,
}


def _update_asset(
    *, identifier: str, config: dict[str, Any], prices_folder: Path
) -> str:
    if not config.get("active", True):
        print(f"[{identifier}] skipped: inactive")
        return "skipped"

    for source in config["waterfall"]:
        fetcher = FETCHERS[source]
        print(f"[{identifier}] trying source={source}")
        try:
            incoming = normalize_price_frame(
                fetcher(identifier, config, HISTORY_DAYS)
            )
        except Exception as exc:
            print(f"[{identifier}] source={source} failed: {exc}")
            continue
        if incoming.empty:
            continue

        path = prices_folder / f"{identifier}.csv"
        merged = merge_price_frames(existing=load_price_csv(path), incoming=incoming)
        if start := config.get("history_start"):
            merged = merged[pd.to_datetime(merged["Date"]) >= pd.Timestamp(start)]
        save_price_csv(frame=merged, file_path=path)
        print(f"[{identifier}] updated via {source}; rows_in_file={len(merged)}")
        return "updated"

    print(f"[{identifier}] failed: source waterfall exhausted")
    return "failed"


def _rebuild_latest_prices(*, context: PortfolioContext) -> pd.DataFrame:
    rows = []
    for path in sorted(context.paths.prices.glob("*.csv")):
        latest = pd.read_csv(path, nrows=1).iloc[0]
        rows.append({"date": latest["Date"], "isin": path.stem, "price": latest["Price"]})
    summary = pd.DataFrame(rows, columns=["date", "isin", "price"]).sort_values("isin")
    atomic_write_csv(frame=summary, path=context.paths.latest_prices)
    return summary


def update_prices(*, context: PortfolioContext) -> int:
    """Update all configured direct prices and rebuild ``latest_prices.csv``."""
    print("Starting market price update...")
    counts = {"updated": 0, "skipped": 0, "failed": 0}
    try:
        metadata = context.currency_metadata() | context.stock_metadata()
        for identifier, config in metadata.items():
            outcome = _update_asset(
                identifier=identifier,
                config=config,
                prices_folder=context.paths.prices,
            )
            counts[outcome] += 1
        summary = _rebuild_latest_prices(context=context)
    except Exception as exc:
        print(f"Market price update failed: {exc}")
        return 1

    print(
        "Market price update finished: "
        f"updated={counts['updated']}, skipped={counts['skipped']}, "
        f"failed={counts['failed']}, summary_rows={len(summary)}"
    )
    return 0
