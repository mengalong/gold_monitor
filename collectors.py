from datetime import date, timedelta
import requests
import pandas as pd
from sqlalchemy import select
from database import SessionLocal, MarketQuote, MacroIndicator, CollectionLog
from config import FRED_API_KEY
from instruments import DOLLAR_INDEX, GOLD_FUTURES, USD_CNY
from market_data import MarketDataProviderChain, YahooFinanceProvider
from security import redact_secrets

YAHOO_SYMBOLS = {
    GOLD_FUTURES: "GC=F",    # COMEX gold futures proxy, not spot XAU/USD
    DOLLAR_INDEX: "DX-Y.NYB",  # Yahoo symbol availability may vary
    USD_CNY: "CNY=X",        # Indicative market quote
}
FRED_SERIES = {
    "DFII10": "percent",
    "DGS10": "percent",
    "CPIAUCSL": "index",
    "PCEPILFE": "index",
}

DEFAULT_MARKET_PROVIDER_CHAIN = MarketDataProviderChain(
    [YahooFinanceProvider(YAHOO_SYMBOLS)]
)

def _log(task, status, message):
    with SessionLocal() as s:
        safe_message = redact_secrets(message, (FRED_API_KEY,))
        s.add(CollectionLog(task=task, status=status, message=safe_message[:4000]))
        s.commit()


def _safe_error(exc):
    return redact_secrets(exc, (FRED_API_KEY,))

def fetch_market_quotes(period="2y", provider_chain=None):
    provider_chain = provider_chain or DEFAULT_MARKET_PROVIDER_CHAIN
    results = {}
    for symbol in YAHOO_SYMBOLS:
        try:
            market_data = provider_chain.fetch_daily(symbol, period)
            history = market_data.frame
            with SessionLocal() as s:
                for _, row in history.iterrows():
                    d = str(row["date"])[:10]
                    close = row.get("close")
                    if pd.isna(close):
                        continue
                    obj = s.scalar(select(MarketQuote).where(
                        MarketQuote.symbol == symbol, MarketQuote.date == d
                    ))
                    values = dict(
                        open=None if pd.isna(row.get("open")) else float(row.get("open")),
                        high=None if pd.isna(row.get("high")) else float(row.get("high")),
                        low=None if pd.isna(row.get("low")) else float(row.get("low")),
                        close=float(close),
                        volume=None if pd.isna(row.get("volume")) else float(row.get("volume")),
                        source=market_data.source,
                    )
                    if obj:
                        for k, v in values.items():
                            setattr(obj, k, v)
                    else:
                        s.add(MarketQuote(symbol=symbol, date=d, **values))
                s.commit()
            results[symbol] = f"成功：{len(history)}条，来源：{market_data.source}"
            _log(f"market:{symbol}", "success", results[symbol])
        except Exception as exc:
            error = _safe_error(exc)
            results[symbol] = f"失败：{error}"
            _log(f"market:{symbol}", "error", error)
    return results


def fetch_yahoo_quotes(period="2y"):
    """Backward-compatible wrapper for the original public function."""
    return fetch_market_quotes(period=period)

def fetch_fred_series():
    if not FRED_API_KEY:
        return {"FRED": "跳过：未配置 FRED_API_KEY"}
    results = {}
    url = "https://api.stlouisfed.org/fred/series/observations"
    for series_id, units in FRED_SERIES.items():
        try:
            params = {
                "series_id": series_id, "api_key": FRED_API_KEY,
                "file_type": "json", "observation_start": (date.today()-timedelta(days=365*5)).isoformat()
            }
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            observations = response.json().get("observations", [])
            with SessionLocal() as s:
                for item in observations:
                    if item["value"] == ".":
                        continue
                    d, value = item["date"], float(item["value"])
                    obj = s.scalar(select(MacroIndicator).where(
                        MacroIndicator.series_id == series_id, MacroIndicator.date == d
                    ))
                    if obj:
                        obj.value, obj.units = value, units
                    else:
                        s.add(MacroIndicator(series_id=series_id, date=d, value=value, units=units))
                s.commit()
            results[series_id] = f"成功：{len(observations)}条"
            _log(f"fred:{series_id}", "success", results[series_id])
        except Exception as exc:
            error = _safe_error(exc)
            results[series_id] = f"失败：{error}"
            _log(f"fred:{series_id}", "error", error)
    return results

def run_daily_update():
    result = {}
    result.update(fetch_market_quotes())
    result.update(fetch_fred_series())
    return result
