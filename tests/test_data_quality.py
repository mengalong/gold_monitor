from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data_quality import FreshnessRule, collect_freshness, evaluate_freshness
from database import Base, MacroIndicator, MarketQuote


RULE = FreshnessRule("market", "GOLD", "黄金", 3)


def test_missing_data_is_reported():
    result = evaluate_freshness(RULE, None, date(2026, 1, 10))

    assert result.status == "missing"
    assert result.age_days is None


def test_recent_data_is_fresh():
    result = evaluate_freshness(RULE, "2026-01-08", date(2026, 1, 10))

    assert result.status == "fresh"
    assert result.age_days == 2


def test_old_data_is_stale():
    result = evaluate_freshness(RULE, "2026-01-05", date(2026, 1, 10))

    assert result.status == "stale"
    assert result.age_days == 5


def test_future_dates_do_not_produce_negative_age():
    result = evaluate_freshness(RULE, "2026-01-11", date(2026, 1, 10))

    assert result.status == "fresh"
    assert result.age_days == 0


def test_freshness_is_collected_from_market_and_macro_tables():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(
            MarketQuote(
                symbol="GOLD",
                date="2026-01-09",
                close=2_500,
                source="test",
            )
        )
        session.add(
            MacroIndicator(
                series_id="REAL_YIELD",
                date="2026-01-01",
                value=2.0,
                units="percent",
                source="test",
            )
        )
        session.commit()

    results = collect_freshness(
        rules=(
            FreshnessRule("market", "GOLD", "黄金", 3),
            FreshnessRule("macro", "REAL_YIELD", "实际利率", 3),
        ),
        as_of=date(2026, 1, 10),
        session_factory=factory,
    )

    assert [item.status for item in results] == ["fresh", "stale"]
