from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from database import PortfolioSnapshot, SessionLocal


@dataclass(frozen=True)
class PortfolioContext:
    total_assets: float
    current_gold_value: float
    max_gold_allocation: float
    remaining_budget: float

    def validate(self):
        errors = []
        if self.total_assets <= 0:
            errors.append("金融资产总额必须大于0")
        if self.current_gold_value < 0:
            errors.append("当前黄金市值不能为负数")
        if not 0 < self.max_gold_allocation <= 1:
            errors.append("黄金配置上限必须在0到100%之间")
        if self.remaining_budget < 0:
            errors.append("剩余黄金预算不能为负数")
        if self.total_assets > 0 and self.current_gold_value > self.total_assets:
            errors.append("当前黄金市值不能超过金融资产总额")
        return errors

    @property
    def current_allocation(self):
        if self.total_assets <= 0:
            return 0.0
        return self.current_gold_value / self.total_assets

    @property
    def allocation_headroom(self):
        return max(0.0, self.total_assets * self.max_gold_allocation - self.current_gold_value)


def save_portfolio(
    context: PortfolioContext,
    snapshot_date: date | None = None,
    note: str = "",
    session_factory=SessionLocal,
):
    errors = context.validate()
    if errors:
        raise ValueError("；".join(errors))
    date_key = (snapshot_date or date.today()).isoformat()
    with session_factory() as session:
        row = session.scalar(
            select(PortfolioSnapshot).where(PortfolioSnapshot.date == date_key)
        )
        values = {
            "total_assets": context.total_assets,
            "current_gold_value": context.current_gold_value,
            "max_gold_allocation": context.max_gold_allocation,
            "remaining_budget": context.remaining_budget,
            "note": note,
        }
        if row:
            for key, value in values.items():
                setattr(row, key, value)
        else:
            row = PortfolioSnapshot(date=date_key, **values)
            session.add(row)
        session.commit()
        return row


def latest_portfolio(session_factory=SessionLocal):
    with session_factory() as session:
        row = session.scalar(
            select(PortfolioSnapshot).order_by(PortfolioSnapshot.date.desc()).limit(1)
        )
        if not row:
            return None
        return PortfolioContext(
            total_assets=row.total_assets,
            current_gold_value=row.current_gold_value,
            max_gold_allocation=row.max_gold_allocation,
            remaining_budget=row.remaining_budget,
        )
