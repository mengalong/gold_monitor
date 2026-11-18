from datetime import date, timedelta
import requests
import pandas as pd
import yfinance as yf
from sqlalchemy import select
from database import SessionLocal, MarketQuote, MacroIndicator, CollectionLog
from config import FRED_API_KEY

YAHOO_SYMBOLS = {
    "XAUUSD": "GC=F",       # COMEX gold futures proxy, not spot XAU/USD
    "DXY": "DX-Y.NYB",      # Yahoo symbol availability may vary
    "USDCNY": "CNY=X",      # Indicative market quote
}
FRED_SERIES = {
    "DFII10": "percent",
    "DGS10": "percent",
    "CPIAUCSL": "index",
    "PCEPILFE": "index",
}

def _log(task, status, message):
    with SessionLocal() as s:
        s.add(CollectionLog(task=task, status=status, message=str(message)[:4000]))
        s.commit()

def fetch_yahoo_quotes(period="2y"):
    results = {}
    for symbol, ticker in YAHOO_SYMBOLS.items():
        try:
            hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
            if hist.empty:
                raise RuntimeError(f"{ticker} returned no rows")
            hist = hist.reset_index()
            date_col = "Date" if "Date" in hist.columns else hist.columns[0]
            with SessionLocal() as s:
                for _, row in hist.iterrows():
                    d = pd.Timestamp(row[date_col]).date().isoformat()
                    close = row.get("Close")
                    if pd.isna(close):
                        continue
                    obj = s.scalar(select(MarketQuote).where(
                        MarketQuote.symbol == symbol, MarketQuote.date == d
                    ))
                    values = dict(
                        open=None if pd.isna(row.get("Open")) else float(row.get("Open")),
                        high=None if pd.isna(row.get("High")) else float(row.get("High")),
                        low=None if pd.isna(row.get("Low")) else float(row.get("Low")),
                        close=float(close),
                        volume=None if pd.isna(row.get("Volume")) else float(row.get("Volume")),
                        source=f"Yahoo Finance ({ticker})",
                    )
                    if obj:
                        for k, v in values.items():
                            setattr(obj, k, v)
                    else:
                        s.add(MarketQuote(symbol=symbol, date=d, **values))
                s.commit()
            results[symbol] = f"成功：{len(hist)}条"
            _log(f"yahoo:{symbol}", "success", results[symbol])
        except Exception as exc:
            results[symbol] = f"失败：{exc}"
            _log(f"yahoo:{symbol}", "error", exc)
    return results

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
            results[series_id] = f"失败：{exc}"
            _log(f"fred:{series_id}", "error", exc)
    return results

def run_daily_update():
    result = {}
    result.update(fetch_yahoo_quotes())
    result.update(fetch_fred_series())
    return result
