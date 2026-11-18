from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from advice import generate_advice, save_advice_snapshot
from data_quality import DataQualityReport
from database import AdviceRecord, Base, SignalSnapshot
from portfolio import PortfolioContext
from signals import SignalResult


def _signal(code, direction, status="complete", metrics=None):
    return SignalResult(
        code=code,
        label=code,
        direction=direction,
        strength={"bullish": 1, "neutral": 0, "bearish": -1, "unavailable": 0}[direction],
        reason=f"{code}:{direction}",
        data_date="2026-01-10" if direction != "unavailable" else None,
        data_status=status,
        metrics=metrics or {},
    )


def _quality(ready=True):
    return DataQualityReport(
        as_of="2026-01-10",
        ready=ready,
        confidence=100.0 if ready else 80.0,
        freshness=(),
        coverage=(),
        blockers=() if ready else ("黄金行情过期",),
    )


PORTFOLIO = PortfolioContext(1_000_000, 80_000, 0.15, 100_000)


def test_failed_quality_gate_pauses_buying():
    signals = tuple(_signal(str(index), "bullish") for index in range(5))

    result = generate_advice(signals, _quality(False), PORTFOLIO)

    assert result.action == "暂停加仓"
    assert result.suggested_amount == 0
    assert "黄金行情过期" in result.blockers


def test_three_bullish_signals_produce_small_probe_amount():
    signals = (
        _signal("a", "bullish"),
        _signal("b", "bullish"),
        _signal("c", "bullish"),
        _signal("d", "neutral"),
        _signal("e", "neutral"),
    )

    result = generate_advice(signals, _quality(), PORTFOLIO)

    assert result.action == "小额试探"
    assert result.budget_ratio == 0.10
    assert result.suggested_amount == 10_000


def test_four_bullish_signals_produce_tranche_amount_with_position_cap():
    portfolio = PortfolioContext(1_000_000, 145_000, 0.15, 100_000)
    signals = tuple(
        [_signal(str(index), "bullish") for index in range(4)]
        + [_signal("neutral", "neutral")]
    )

    result = generate_advice(signals, _quality(), portfolio)

    assert result.action == "分批加仓"
    assert result.suggested_amount == 5_000


def test_two_bearish_signals_trigger_veto():
    signals = (
        _signal("real_yield", "bearish"),
        _signal("dollar", "bearish"),
        _signal("a", "bullish"),
        _signal("b", "bullish"),
        _signal("c", "bullish"),
    )

    result = generate_advice(signals, _quality(), PORTFOLIO)

    assert result.action == "暂停加仓"
    assert any("2 个偏空" in blocker for blocker in result.blockers)


def test_buy_signal_without_portfolio_is_blocked():
    signals = tuple(_signal(str(index), "bullish") for index in range(5))

    result = generate_advice(signals, _quality(), None)

    assert result.action == "暂停加仓"
    assert any("尚未配置" in blocker for blocker in result.blockers)


def test_advice_and_signals_are_upserted_for_same_day():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    signals = tuple(_signal(str(index), "bullish") for index in range(5))
    advice = generate_advice(signals, _quality(), PORTFOLIO)

    save_advice_snapshot(advice, signals, date(2026, 1, 10), factory)
    save_advice_snapshot(advice, signals, date(2026, 1, 10), factory)

    with factory() as session:
        assert len(session.scalars(select(AdviceRecord)).all()) == 1
        assert len(session.scalars(select(SignalSnapshot)).all()) == 5
