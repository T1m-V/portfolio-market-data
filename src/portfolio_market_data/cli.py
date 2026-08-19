from __future__ import annotations

import argparse
from pathlib import Path

from portfolio_core import PortfolioContext, mutation_session, validate_data_workspace


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="portfolio-market")
    parser.add_argument("--data-dir", type=Path, required=True)
    domains = parser.add_subparsers(dest="domain", required=True)

    prices = domains.add_parser("prices")
    prices.add_subparsers(dest="action", required=True).add_parser("update")

    transactions = domains.add_parser("transactions")
    transaction_actions = transactions.add_subparsers(dest="action", required=True)
    update = transaction_actions.add_parser("update")
    update.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    context = PortfolioContext.from_root(args.data_dir)
    validate_data_workspace(context.paths.root)

    with context.activate(), mutation_session(paths=context.paths):
        if args.domain == "prices":
            from portfolio_market_data.prices import update_prices

            return update_prices(context=context)

        from portfolio_market_data.transactions import update_transactions

        update_transactions(context=context, transaction_limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
