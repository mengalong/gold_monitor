import numpy as np
import pandas as pd

def rsi(series: pd.Series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.sort_values("date").copy()
    close = out["close"].astype(float)
    for n in (20, 60, 120, 250):
        out[f"ma{n}"] = close.rolling(n).mean()
    out["rsi14"] = rsi(close, 14)
    ema12, ema26 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    out["bb_upper"], out["bb_lower"] = mid + 2*std, mid - 2*std
    prev_close = close.shift(1)
    tr = pd.concat([
        out["high"].astype(float)-out["low"].astype(float),
        (out["high"].astype(float)-prev_close).abs(),
        (out["low"].astype(float)-prev_close).abs()
    ], axis=1).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    out["return_1d"] = close.pct_change()*100
    out["return_20d"] = close.pct_change(20)*100
    return out
