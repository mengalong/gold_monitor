from dataclasses import dataclass
from typing import Protocol

import pandas as pd
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
