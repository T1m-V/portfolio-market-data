from __future__ import annotations

from portfolio_core import PortfolioContext

from portfolio_market_data.transactions.add_stock_splits import download_splits
from portfolio_market_data.transactions.get_getquin_transactions import (
    DEFAULT_TRANSACTION_LIMIT,
    download_transactions,
)
from portfolio_market_data.transactions.portfolio_snapshots import generate_portfolio_snapshots
from portfolio_market_data.transactions.transform_data import convert_transaction_json_to_csv


def update_transactions(
    *,
    context: PortfolioContext,
    transaction_limit: int = DEFAULT_TRANSACTION_LIMIT,
) -> None:
    """Refresh Getquin exports, normalized transactions, and portfolio snapshots."""
    paths = context.paths
    token = context.getquin_token()
    print("Starting market transaction update...")

    download_transactions(
        output_file=paths.transaction_export,
        token=token,
        limit=transaction_limit,
    )
    download_splits(
        transaction_file=paths.transaction_export,
        output_file=paths.stock_split_export,
        token=token,
    )
    convert_transaction_json_to_csv(
        tx_file=paths.transaction_export,
        split_file=paths.stock_split_export,
        output_file=paths.normalized_transactions,
    )
    generate_portfolio_snapshots(
        input_csv=paths.normalized_transactions,
        output_csv=paths.portfolio_snapshot,
        stock_metadata=context.stock_metadata(),
        prices_folder=paths.prices,
    )
    print("Market transaction update finished successfully.")
