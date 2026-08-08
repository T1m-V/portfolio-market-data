from pathlib import Path

from portfolio_core import PortfolioContext

from portfolio_market_data.transactions import update


def test_transaction_update_passes_requested_getquin_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    context = PortfolioContext.from_root(tmp_path, load_secrets=False)
    monkeypatch.setattr(context.__class__, "getquin_token", lambda self: "test-token")
    calls = []

    def download_transactions(*, output_file, token, limit):
        calls.append(("download", output_file, token, limit))

    def download_splits(*, transaction_file, output_file, token):
        calls.append(("splits", transaction_file, output_file, token))

    def convert_transaction_json_to_csv(*, tx_file, split_file, output_file):
        calls.append(("convert", tx_file, split_file, output_file))

    def generate_portfolio_snapshots(
        *, input_csv, output_csv, stock_metadata, prices_folder
    ):
        calls.append(
            ("snapshots", input_csv, output_csv, stock_metadata, prices_folder)
        )

    monkeypatch.setattr(update, "download_transactions", download_transactions)
    monkeypatch.setattr(update, "download_splits", download_splits)
    monkeypatch.setattr(update, "convert_transaction_json_to_csv", convert_transaction_json_to_csv)
    monkeypatch.setattr(update, "generate_portfolio_snapshots", generate_portfolio_snapshots)

    update.update_transactions(context=context, transaction_limit=500)

    assert calls[0] == (
        "download",
        context.paths.transaction_export,
        "test-token",
        500,
    )
