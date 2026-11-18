from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data_quality import (
    CoverageRule,
    FreshnessRule,
    assess_core_data_quality,
    collect_coverage,
    collect_freshness,
    evaluate_freshness,
)
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


def test_coverage_counts_only_points_inside_window():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add_all(
            [
                MarketQuote(symbol="GOLD", date="2026-01-09", close=2_500, source="test"),
                MarketQuote(symbol="GOLD", date="2025-12-01", close=2_400, source="test"),
            ]
        )
        session.commit()

    result = collect_coverage(
        rules=(CoverageRule("market", "GOLD", "黄金", 10, 2),),
        as_of=date(2026, 1, 10),
        session_factory=factory,
    )[0]

    assert result.available_points == 1
    assert result.status == "insufficient"


def test_quality_gate_lists_freshness_and_coverage_blockers():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(MarketQuote(symbol="GOLD", date="2026-01-09", close=2_500, source="test"))
        session.commit()

    report = assess_core_data_quality(
        as_of=date(2026, 1, 10),
        freshness_rules=(
            FreshnessRule("market", "GOLD", "黄金", 3),
            FreshnessRule("macro", "REAL_YIELD", "实际利率", 3),
        ),
        coverage_rules=(CoverageRule("market", "GOLD", "黄金", 10, 2),),
        session_factory=factory,
    )

    assert report.ready is False
    assert report.confidence == 33.3
    assert "实际利率数据缺失" in report.blockers
    assert any("至少需要 2 条" in blocker for blocker in report.blockers)
