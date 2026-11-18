import numpy as np
import pandas as pd

from signals import (
    dollar_signal,
    domestic_premium_signal,
    flow_signal,
    gold_trend_signal,
    real_yield_signal,
)


def _frame(values, column="close", start="2025-01-01"):
    return pd.DataFrame(
        {
            "date": pd.date_range(start, periods=len(values)).astype(str),
            column: values,
        }
    )


def test_falling_real_yield_is_bullish():
    result = real_yield_signal(_frame(np.linspace(2.0, 1.7, 21), column="value"))

    assert result.direction == "bullish"
    assert result.metrics["change_20"] == -0.3


def test_rising_dollar_above_ma60_is_bearish():
    values = np.concatenate([np.full(39, 100.0), np.linspace(100.0, 103.0, 21)])
    result = dollar_signal(_frame(values))

    assert result.direction == "bearish"
    assert result.metrics["return_20_pct"] >= 1.5


def test_confirmed_gold_uptrend_is_bullish():
    result = gold_trend_signal(_frame(np.linspace(1800.0, 2600.0, 240)))

    assert result.direction == "bullish"
    assert result.metrics["current"] > result.metrics["ma200"]


def test_missing_fund_flow_data_is_unavailable():
    result = flow_signal(pd.DataFrame(), pd.DataFrame())

    assert result.direction == "unavailable"
    assert result.data_status == "missing"


def test_one_fund_flow_source_is_marked_partial():
    etf = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22"],
            "value1": [1.0, 2.0, -0.5, 1.5],
        }
    )

    result = flow_signal(etf, pd.DataFrame())

    assert result.direction == "bullish"
    assert result.data_status == "partial"


def test_high_domestic_premium_percentile_is_bearish():
    dates = pd.date_range("2026-01-01", periods=30).astype(str)
    gold = pd.DataFrame({"date": dates, "close": np.full(30, 3000.0)})
    fx = pd.DataFrame({"date": dates, "close": np.full(30, 7.0)})
    theoretical = 3000.0 * 7.0 / 31.1034768
    premiums = np.linspace(-1.0, 2.0, 30)
    sge = pd.DataFrame(
        {"date": dates, "close": theoretical * (1 + premiums / 100)}
    )

    result = domestic_premium_signal(sge, gold, fx)

    assert result.direction == "bearish"
    assert result.metrics["premium_percentile"] == 100.0
