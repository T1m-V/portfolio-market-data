import importlib
import sys

import portfolio_core as file_paths


def test_transaction_robot_passes_requested_getquin_limit(monkeypatch) -> None:
    monkeypatch.setattr(file_paths, "get_token", lambda: "test-token")
    sys.modules.pop("portfolio_market_data.transactions.add_stock_splits", None)
    sys.modules.pop("portfolio_market_data.transactions.transaction_robot", None)
    transaction_robot = importlib.import_module(
        "portfolio_market_data.transactions.transaction_robot"
    )

    calls = []

    def download_transactions(*, output_file, limit):
        calls.append(("download", output_file, limit))

    def download_splits(*, transaction_file, output_file):
        calls.append(("splits", transaction_file, output_file))

    def convert_transaction_json_to_csv(*, tx_file, split_file, output_file):
        calls.append(("convert", tx_file, split_file, output_file))

    def generate_portfolio_snapshots(*, input_csv, output_csv):
        calls.append(("snapshots", input_csv, output_csv))

    monkeypatch.setattr(transaction_robot, "download_transactions", download_transactions)
    monkeypatch.setattr(transaction_robot, "download_splits", download_splits)
    monkeypatch.setattr(
        transaction_robot,
        "convert_transaction_json_to_csv",
        convert_transaction_json_to_csv,
    )
    monkeypatch.setattr(
        transaction_robot,
        "generate_portfolio_snapshots",
        generate_portfolio_snapshots,
    )

    transaction_robot.main(transaction_limit=500)

    assert calls[0] == ("download", transaction_robot.TRANSACTION_JSON_PATH, 500)
