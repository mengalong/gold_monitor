from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from portfolio import PortfolioContext, latest_portfolio, save_portfolio


def _factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_portfolio_calculates_allocation_and_headroom():
    context = PortfolioContext(
        total_assets=1_000_000,
        current_gold_value=80_000,
        max_gold_allocation=0.15,
        remaining_budget=100_000,
    )

    assert context.current_allocation == 0.08
    assert context.allocation_headroom == 70_000
    assert context.validate() == []


def test_invalid_portfolio_is_rejected():
    context = PortfolioContext(0, -1, 1.2, -10)

    assert len(context.validate()) == 4


def test_same_day_snapshot_is_updated_and_latest_can_be_read():
    factory = _factory()
    first = PortfolioContext(1_000_000, 80_000, 0.15, 100_000)
    updated = PortfolioContext(1_000_000, 90_000, 0.15, 90_000)

    save_portfolio(first, date(2026, 1, 2), session_factory=factory)
    save_portfolio(updated, date(2026, 1, 2), session_factory=factory)

    assert latest_portfolio(factory) == updated
