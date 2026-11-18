import numpy as np
import pandas as pd

from indicators import add_technical_indicators, rsi


def _price_frame(rows=300):
    index = np.arange(rows)
    close = 2_000 + index * 0.8 + np.sin(index / 8) * 20
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=rows).astype(str),
            "open": close - 2,
            "high": close + 5,
            "low": close - 5,
            "close": close,
            "volume": 1_000 + index,
        }
    )


def test_rsi_stays_within_expected_range():
    values = rsi(_price_frame()["close"])
    available = values.dropna()

    assert not available.empty
    assert available.between(0, 100).all()


def test_all_expected_technical_indicators_are_calculated():
    result = add_technical_indicators(_price_frame())

    expected = {
        "ma20",
        "ma60",
        "ma120",
        "ma250",
        "rsi14",
        "macd",
        "macd_signal",
        "macd_hist",
        "bb_upper",
        "bb_lower",
        "atr14",
        "return_1d",
        "return_20d",
    }
    assert expected.issubset(result.columns)
    assert pd.notna(result.iloc[-1]["ma250"])
    assert pd.notna(result.iloc[-1]["atr14"])
