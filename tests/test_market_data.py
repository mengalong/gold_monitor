from datetime import date

import pandas as pd
import pytest

from market_data import (
    FREDMarketProvider,
    MarketDataProviderChain,
    MarketDataResult,
    MarketDataUnavailable,
    YahooChartProvider,
    _normalize_fred_observations,
    _normalize_yahoo_chart,
    _normalize_yahoo_history,
    _observation_start,
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


def test_yahoo_chart_is_normalized_and_missing_close_is_removed():
    result = _normalize_yahoo_chart(
        {
            "meta": {"exchangeTimezoneName": "America/New_York"},
            "timestamp": [1767358800, 1767618000],
            "indicators": {
                "quote": [
                    {
                        "open": [2500.0, None],
                        "high": [2520.0, None],
                        "low": [2490.0, None],
                        "close": [2510.0, None],
                        "volume": [100.0, None],
                    }
                ]
            },
        }
    )

    assert len(result) == 1
    assert result.iloc[0]["close"] == 2510.0


def test_yahoo_chart_provider_builds_encoded_request():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {"exchangeTimezoneName": "UTC"},
                            "timestamp": [1767312000],
                            "indicators": {"quote": [{"close": [2510.0]}]},
                        }
                    ],
                    "error": None,
                }
            }

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    provider = YahooChartProvider({"GOLD": "GC=F"}, http_get=fake_get)
    result = provider.fetch_daily("GOLD", "2y")

    assert calls[0][0].endswith("/GC%3DF")
    assert calls[0][1]["params"]["range"] == "2y"
    assert result.source == "Yahoo Finance Chart (GC=F)"
    assert result.frame.iloc[0]["close"] == 2510.0


def test_fred_observations_skip_missing_values():
    result = _normalize_fred_observations(
        [
            {"date": "2026-01-02", "value": "7.1234"},
            {"date": "2026-01-03", "value": "."},
        ]
    )

    assert result.to_dict("records") == [
        {
            "date": "2026-01-02",
            "open": None,
            "high": None,
            "low": None,
            "close": 7.1234,
            "volume": None,
        }
    ]


def test_fred_period_is_converted_to_observation_start():
    assert _observation_start("2y", date(2026, 1, 1)) == date(2024, 1, 2)
    assert _observation_start("6mo", date(2026, 7, 1)) == date(2025, 12, 27)


def test_fred_provider_requires_api_key():
    provider = FREDMarketProvider({"USDCNY": "DEXCHUS"}, "")

    with pytest.raises(MarketDataUnavailable, match="FRED_API_KEY"):
        provider.fetch_daily("USDCNY", "2y")


def test_fred_provider_returns_normalized_exchange_rate():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"observations": [{"date": "2026-01-02", "value": "7.1234"}]}

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    provider = FREDMarketProvider(
        {"USDCNY": "DEXCHUS"},
        "test-key",
        http_get=fake_get,
    )

    result = provider.fetch_daily("USDCNY", "2y")

    assert result.source == "FRED (DEXCHUS)"
    assert result.frame.iloc[0]["close"] == 7.1234
    assert calls[0][1]["params"]["series_id"] == "DEXCHUS"
    assert calls[0][1]["params"]["api_key"] == "test-key"
