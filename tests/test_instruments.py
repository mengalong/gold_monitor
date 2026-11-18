from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from collectors import YAHOO_SYMBOLS
from database import Base, MarketQuote, _migrate_legacy_gold_symbol
from instruments import DOLLAR_INDEX, GOLD_FUTURES, GOLD_SPOT, USD_CNY


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_internal_instrument_codes_are_unambiguous():
    assert GOLD_FUTURES != GOLD_SPOT
    assert YAHOO_SYMBOLS[GOLD_FUTURES] == "GC=F"
    assert YAHOO_SYMBOLS[DOLLAR_INDEX] == "DX-Y.NYB"
    assert YAHOO_SYMBOLS[USD_CNY] == "CNY=X"


def test_legacy_gc_futures_rows_are_migrated_without_touching_spot_rows():
    factory = _session_factory()
    with factory() as session:
        session.add_all(
            [
                MarketQuote(
                    symbol=GOLD_SPOT,
                    date="2026-01-02",
                    close=2_500,
                    source="Yahoo Finance (GC=F)",
                ),
                MarketQuote(
                    symbol=GOLD_SPOT,
                    date="2026-01-03",
                    close=2_510,
                    source="Spot provider",
                ),
            ]
        )
        session.commit()

    _migrate_legacy_gold_symbol(factory)

    with factory() as session:
        futures = session.scalars(
            select(MarketQuote).where(MarketQuote.symbol == GOLD_FUTURES)
        ).all()
        spot = session.scalars(
            select(MarketQuote).where(MarketQuote.symbol == GOLD_SPOT)
        ).all()

    assert [row.date for row in futures] == ["2026-01-02"]
    assert [row.date for row in spot] == ["2026-01-03"]
