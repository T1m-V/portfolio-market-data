import json
from pathlib import Path

import pandas as pd
from portfolio_core import PortfolioContext

from portfolio_market_data import prices


class _Response:
    text = ""

    def __init__(self, data: dict | None = None) -> None:
        self.data = data or {}

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self.data


def test_provider_adapters_return_date_and_price(monkeypatch) -> None:
    yahoo_history = pd.DataFrame(
        {"Close": [12.5]},
        index=pd.DatetimeIndex(["2026-08-07"], name="Date", tz="Europe/Amsterdam"),
    )

    class YahooTicker:
        def history(self, **kwargs) -> pd.DataFrame:
            return yahoo_history

    class MorningstarFund:
        def nav(self, **kwargs) -> list[dict]:
            return [{"date": "2026-08-07", "nav": 13.5}]

    monkeypatch.setattr(prices.yf, "Ticker", lambda ticker: YahooTicker())
    monkeypatch.setattr(prices.mstarpy, "Funds", lambda term: MorningstarFund())
    monkeypatch.setattr(
        prices.pd,
        "read_html",
        lambda html: [pd.DataFrame({"Date": ["Aug 07 2026 Aug 06 2026"], "Close": ["1,234.5"]})],
    )
    monkeypatch.setattr(prices.requests, "get", lambda *args, **kwargs: _Response())

    yahoo = prices._fetch_yahoo("ASSET", {"ticker": "TEST"}, 10)
    morningstar = prices._fetch_morningstar("ASSET", {}, 10)
    ft = prices._fetch_ft("ASSET", {}, 10)

    assert yahoo.iloc[0].to_dict() == {"Date": pd.Timestamp("2026-08-07"), "Price": 12.5}
    assert morningstar.iloc[0].to_dict() == {"Date": "2026-08-07", "Price": 13.5}
    assert ft.iloc[0].to_dict() == {"Date": "Aug 07 2026", "Price": "1234.5"}


def test_llama_adapter_collects_available_daily_prices(monkeypatch) -> None:
    responses = iter(
        [
            _Response({"coins": {"chain:token": {"price": 2.0}}}),
            _Response({"coins": {}}),
        ]
    )
    monkeypatch.setattr(prices.requests, "get", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(prices.time, "sleep", lambda seconds: None)

    result = prices._fetch_llama("ASSET", {"ticker": "chain:token"}, 2)

    assert result["Price"].tolist() == [2.0]


def test_price_update_uses_waterfall_and_rebuilds_latest_summary(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    config = tmp_path / "config"
    prices_dir = tmp_path / "prices"
    config.mkdir()
    prices_dir.mkdir()
    (config / "stock_metadata.json").write_text(
        json.dumps(
            {
                "ACTIVE": {
                    "ticker": "ACTIVE",
                    "waterfall": ["Evi", "Yahoo"],
                    "history_start": "2026-01-02",
                },
                "INACTIVE": {"active": False, "waterfall": ["Yahoo"]},
            }
        ),
        encoding="utf-8",
    )
    (config / "currency_metadata.json").write_text("{}", encoding="utf-8")
    pd.DataFrame({"Date": ["2026-01-01"], "Price": [1]}).to_csv(
        prices_dir / "ACTIVE.csv", index=False
    )
    pd.DataFrame({"Date": ["2025-01-01"], "Price": [2]}).to_csv(
        prices_dir / "INACTIVE.csv", index=False
    )
    monkeypatch.setitem(
        prices.FETCHERS,
        "Yahoo",
        lambda identifier, metadata, days: pd.DataFrame(
            {"Date": ["2026-01-03"], "Price": [3]}
        ),
    )

    context = PortfolioContext.from_root(tmp_path, load_secrets=False)
    assert prices.update_prices(context=context) == 0

    assert pd.read_csv(prices_dir / "ACTIVE.csv").to_dict("records") == [
        {"Date": "2026-01-03", "Price": 3}
    ]
    latest = pd.read_csv(tmp_path / "latest_prices.csv")
    assert latest[["isin", "price"]].to_dict("records") == [
        {"isin": "ACTIVE", "price": 3},
        {"isin": "INACTIVE", "price": 2},
    ]
    assert "skipping unsupported source=Evi" in capsys.readouterr().out
