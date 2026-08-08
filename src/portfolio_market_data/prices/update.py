from __future__ import annotations

from portfolio_core import PortfolioContext

from portfolio_market_data.prices.retrieve_last_prices import generate_latest_prices_summary
from portfolio_market_data.prices.update_all_prices import update_portfolio_prices


def update_prices(*, context: PortfolioContext) -> int:
    """Update direct price histories and rebuild the latest-price summary."""
    print("Starting market price update...")
    try:
        update_results = update_portfolio_prices(context=context)
        summary_frame = generate_latest_prices_summary(paths=context.paths)
    except Exception as exc:
        print(f"Market price update failed: {exc}")
        return 1

    success_count = sum(result.success for result in update_results)
    skipped_count = sum(result.skipped for result in update_results)
    failed_count = len(update_results) - success_count - skipped_count
    print(
        "Market price update finished: "
        f"updated={success_count}, skipped={skipped_count}, failed={failed_count}, "
        f"summary_rows={len(summary_frame)}"
    )
    return 0
