from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import pandas as pd
import requests
import yfinance as yf


class MarketDataUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class MarketDataResult:
    frame: pd.DataFrame
    source: str


class MarketDataProvider(Protocol):
    name: str

    def supports(self, symbol: str) -> bool:
        ...

    def fetch_daily(self, symbol: str, period: str) -> MarketDataResult:
        ...


class YahooFinanceProvider:
    name = "Yahoo Finance"

    def __init__(self, tickers: dict[str, str]):
        self.tickers = tickers

    def supports(self, symbol: str) -> bool:
        return symbol in self.tickers

    def fetch_daily(self, symbol: str, period: str) -> MarketDataResult:
        ticker = self.tickers[symbol]
        history = yf.Ticker(ticker).history(
            period=period,
            interval="1d",
            auto_adjust=False,
        )
        if history.empty:
            raise MarketDataUnavailable(f"{ticker} returned no rows")
        return MarketDataResult(
            frame=_normalize_yahoo_history(history),
            source=f"{self.name} ({ticker})",
        )


class FREDMarketProvider:
    name = "FRED"
    api_url = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, series: dict[str, str], api_key: str, http_get=requests.get):
        self.series = series
        self.api_key = api_key
        self.http_get = http_get

    def supports(self, symbol: str) -> bool:
        return symbol in self.series

    def fetch_daily(self, symbol: str, period: str) -> MarketDataResult:
        if not self.api_key:
            raise MarketDataUnavailable("未配置 FRED_API_KEY")
        series_id = self.series[symbol]
        response = self.http_get(
            self.api_url,
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": _observation_start(period).isoformat(),
            },
            timeout=30,
        )
        response.raise_for_status()
        observations = response.json().get("observations", [])
        frame = _normalize_fred_observations(observations)
        if frame.empty:
            raise MarketDataUnavailable(f"{series_id} 未返回有效数据")
        return MarketDataResult(frame=frame, source=f"{self.name} ({series_id})")


class MarketDataProviderChain:
    def __init__(self, providers: list[MarketDataProvider]):
        self.providers = providers

    def fetch_daily(self, symbol: str, period: str) -> MarketDataResult:
        errors = []
        supported = False
        for provider in self.providers:
            if not provider.supports(symbol):
                continue
            supported = True
            try:
                return provider.fetch_daily(symbol, period)
            except Exception as exc:
                errors.append(f"{provider.name}: {exc}")

        if not supported:
            raise MarketDataUnavailable(f"没有支持 {symbol} 的行情提供器")
        raise MarketDataUnavailable("；".join(errors))


def _normalize_yahoo_history(history: pd.DataFrame) -> pd.DataFrame:
    source = history.reset_index()
    date_column = "Date" if "Date" in source.columns else source.columns[0]
    normalized = pd.DataFrame(
        {
            "date": pd.to_datetime(source[date_column]).dt.date.astype(str),
            "open": source.get("Open"),
            "high": source.get("High"),
            "low": source.get("Low"),
            "close": source.get("Close"),
            "volume": source.get("Volume"),
        }
    )
    return normalized.dropna(subset=["close"]).reset_index(drop=True)


def _normalize_fred_observations(observations) -> pd.DataFrame:
    records = []
    for item in observations:
        value = item.get("value")
        if value in {None, "."}:
            continue
        records.append(
            {
                "date": item["date"],
                "open": None,
                "high": None,
                "low": None,
                "close": float(value),
                "volume": None,
            }
        )
    return pd.DataFrame(
        records,
        columns=["date", "open", "high", "low", "close", "volume"],
    )


def _observation_start(period: str, today: date | None = None) -> date:
    today = today or date.today()
    if period == "max":
        return date(1970, 1, 1)
    if period.endswith("y") and period[:-1].isdigit():
        return today - timedelta(days=365 * int(period[:-1]))
    if period.endswith("mo") and period[:-2].isdigit():
        return today - timedelta(days=31 * int(period[:-2]))
    raise ValueError(f"FRED 不支持行情周期：{period}")
