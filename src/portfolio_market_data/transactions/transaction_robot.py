from portfolio_core import (
    SNAPSHOT_FILE_PATH,
    STOCK_SPLIT_JSON_PATH,
    TRANSACTION_JSON_PATH,
    TRANSACTIONS_FILE_PATH,
)

from portfolio_market_data.transactions.add_stock_splits import download_splits
from portfolio_market_data.transactions.get_getquin_transactions import (
    DEFAULT_TRANSACTION_LIMIT,
    download_transactions,
)
from portfolio_market_data.transactions.portfolio_snapshots import generate_portfolio_snapshots
from portfolio_market_data.transactions.transform_data import convert_transaction_json_to_csv


def main(transaction_limit: int = DEFAULT_TRANSACTION_LIMIT):
    print("🚀 Starting Transaction Robot...")

    # Step 1: Update all transactions and splits.
    print("\nStep 1: Updating historical transaction data...")
    download_transactions(output_file=TRANSACTION_JSON_PATH, limit=transaction_limit)
    download_splits(transaction_file=TRANSACTION_JSON_PATH, output_file=STOCK_SPLIT_JSON_PATH)

    # Step 2: Generate the summary 'latest_prices.csv'
    print("\nStep 2: Create transaction .csv file...")
    convert_transaction_json_to_csv(
        tx_file=TRANSACTION_JSON_PATH,
        split_file=STOCK_SPLIT_JSON_PATH,
        output_file=TRANSACTIONS_FILE_PATH,
    )

    print("\nStep 3: Make portfolio snapshots for all dates...")
    generate_portfolio_snapshots(input_csv=TRANSACTIONS_FILE_PATH, output_csv=SNAPSHOT_FILE_PATH)

    print("\n✨ Transaction Robot finished successfully.")


if __name__ == "__main__":
    main()
