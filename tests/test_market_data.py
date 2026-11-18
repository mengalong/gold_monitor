import pandas as pd
import pytest

from market_data import (
    MarketDataProviderChain,
    MarketDataResult,
    MarketDataUnavailable,
    _normalize_yahoo_history,
)


class FakeProvider:
    def __init__(self, name, result=None, error=None, symbols=None):
        self.name = name
        self.result = result
        self.error = error
        self.symbols = symbols or {"GOLD"}
        self.calls = []

    def supports(self, symbol):
        return symbol in self.symbols

    def fetch_daily(self, symbol, period):
        self.calls.append((symbol, period))
        if self.error:
            raise self.error
        return self.result


def test_provider_chain_falls_back_after_first_provider_fails():
    expected = MarketDataResult(
        frame=pd.DataFrame([{"date": "2026-01-02", "close": 2_500}]),
        source="备用源",
    )
    primary = FakeProvider("主数据源", error=RuntimeError("限流"))
    fallback = FakeProvider("备用源", result=expected)

    result = MarketDataProviderChain([primary, fallback]).fetch_daily("GOLD", "2y")

    assert result is expected
    assert primary.calls == [("GOLD", "2y")]
    assert fallback.calls == [("GOLD", "2y")]


def test_provider_chain_reports_all_failures():
    chain = MarketDataProviderChain(
        [
            FakeProvider("主数据源", error=RuntimeError("限流")),
            FakeProvider("备用源", error=RuntimeError("无数据")),
        ]
    )

    with pytest.raises(MarketDataUnavailable) as exc_info:
        chain.fetch_daily("GOLD", "2y")

    assert "主数据源: 限流" in str(exc_info.value)
    assert "备用源: 无数据" in str(exc_info.value)


def test_yahoo_history_is_normalized_to_internal_columns():
    index = pd.DatetimeIndex(["2026-01-02", "2026-01-03"], name="Date")
    history = pd.DataFrame(
        {
            "Open": [2_490.0, 2_500.0],
            "High": [2_510.0, 2_520.0],
            "Low": [2_480.0, 2_490.0],
            "Close": [2_500.0, 2_510.0],
            "Volume": [100.0, 120.0],
        },
        index=index,
    )

    result = _normalize_yahoo_history(history)

    assert result.columns.tolist() == ["date", "open", "high", "low", "close", "volume"]
    assert result["date"].tolist() == ["2026-01-02", "2026-01-03"]
