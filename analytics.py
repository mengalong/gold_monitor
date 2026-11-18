import pandas as pd
from sqlalchemy import select
from database import SessionLocal, MarketQuote, MacroIndicator, ImportedDatum, ScoreRecord
from instruments import DOLLAR_INDEX, GOLD_FUTURES

OZ_TO_GRAM = 31.1034768

def quotes_df(symbol):
    with SessionLocal() as s:
        rows = s.scalars(select(MarketQuote).where(MarketQuote.symbol == symbol).order_by(MarketQuote.date)).all()
        return pd.DataFrame([{"date": r.date, "open": r.open, "high": r.high, "low": r.low,
                              "close": r.close, "volume": r.volume, "source": r.source} for r in rows])

def macro_df(series_id):
    with SessionLocal() as s:
        rows = s.scalars(select(MacroIndicator).where(MacroIndicator.series_id == series_id).order_by(MacroIndicator.date)).all()
        return pd.DataFrame([{"date": r.date, "value": r.value, "units": r.units} for r in rows])

def imported_df(dataset):
    with SessionLocal() as s:
        rows = s.scalars(select(ImportedDatum).where(ImportedDatum.dataset == dataset).order_by(ImportedDatum.date)).all()
        return pd.DataFrame([{"date": r.date, "key": r.key, "value1": r.value1, "value2": r.value2,
                              "value3": r.value3, "value4": r.value4} for r in rows])

def calculate_domestic_theoretical(international_usd, usdcny):
    return international_usd * usdcny / OZ_TO_GRAM

def build_score():
    # Transparent starter heuristic. Not a backtested trading signal.
    gold = quotes_df(GOLD_FUTURES)
    dxy = quotes_df(DOLLAR_INDEX)
    real = macro_df("DFII10")
    if gold.empty:
        return None
    date_key = gold.iloc[-1]["date"]
    macro_score = 50.0
    if len(real) >= 21:
        delta = real.iloc[-1]["value"] - real.iloc[-21]["value"]
        macro_score = 75 if delta < -0.15 else 25 if delta > 0.15 else 50
    if len(dxy) >= 21:
        delta = dxy.iloc[-1]["close"] / dxy.iloc[-21]["close"] - 1
        macro_score = max(0, min(100, macro_score + (-delta*100*2)))
    tech_score = 50.0
    if len(gold) >= 60:
        close = gold["close"]
        ma20, ma60 = close.rolling(20).mean().iloc[-1], close.rolling(60).mean().iloc[-1]
        tech_score = 75 if close.iloc[-1] > ma20 > ma60 else 25 if close.iloc[-1] < ma20 < ma60 else 50
    flows_score = 50.0  # until WGC/COT datasets are imported and modeled
    domestic_score = 50.0
    total = macro_score*.40 + flows_score*.30 + tech_score*.20 + domestic_score*.10
    with SessionLocal() as s:
        obj = s.scalar(select(ScoreRecord).where(ScoreRecord.date == date_key))
        values = dict(macro_score=macro_score, flows_score=flows_score, technical_score=tech_score,
                      domestic_score=domestic_score, total_score=total,
                      note="第一版启发式评分；资金流与国内溢价暂以中性占位，尚未回测。")
        if obj:
            for k,v in values.items(): setattr(obj,k,v)
        else:
            s.add(ScoreRecord(date=date_key, **values))
        s.commit()
    return {"date": date_key, "macro": macro_score, "flows": flows_score, "technical": tech_score,
            "domestic": domestic_score, "total": total}
