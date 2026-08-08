from pathlib import Path

import pandas as pd
from portfolio_core import PortfolioPaths, atomic_write_csv

SUMMARY_COLUMNS = ["date", "isin", "price"]


def _list_price_files(price_folder: Path) -> list[Path]:
    return sorted(price_folder.glob("*.csv"))


def _read_latest_row(file_path: Path) -> dict[str, str | float] | None:
    try:
        frame = pd.read_csv(file_path, nrows=1)
    except Exception as exc:
        print(f"Skipping {file_path.name}: {exc}")
        return None

    if frame.empty:
        return None

    return {
        "date": frame.iloc[0]["Date"],
        "isin": file_path.stem,
        "price": frame.iloc[0]["Price"],
    }


def generate_latest_prices_summary(*, paths: PortfolioPaths) -> pd.DataFrame:
    """
    Reads all local price CSV files and writes latest_prices.csv.

    returns:
        Generated summary frame.
    """
    if not paths.prices.exists():
        print("Price data directory does not exist.")
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    csv_files = _list_price_files(price_folder=paths.prices)
    if not csv_files:
        print("No price files found to summarize.")
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    print(f"Generating latest summary for {len(csv_files)} assets...")

    summary_rows = []
    for file_path in csv_files:
        row = _read_latest_row(file_path=file_path)
        if row is not None:
            summary_rows.append(row)

    summary_frame = pd.DataFrame(summary_rows, columns=SUMMARY_COLUMNS)
    if summary_frame.empty:
        summary_frame = pd.DataFrame(columns=SUMMARY_COLUMNS)
    else:
        summary_frame = summary_frame.sort_values(by="isin", ascending=True)

    atomic_write_csv(frame=summary_frame, path=paths.latest_prices)
    print(f"Summary saved to: {paths.latest_prices}")
    return summary_frame
