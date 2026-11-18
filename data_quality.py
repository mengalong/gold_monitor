from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import func, select

from database import MacroIndicator, MarketQuote, SessionLocal
from instruments import DOLLAR_INDEX, GOLD_FUTURES, SGE_AU9999, USD_CNY


@dataclass(frozen=True)
class FreshnessRule:
    dataset_type: str
    code: str
    label: str
    max_age_days: int


@dataclass(frozen=True)
class FreshnessResult:
    dataset_type: str
    code: str
    label: str
    latest_date: str | None
    age_days: int | None
    max_age_days: int
    status: str

    def to_dict(self):
        return asdict(self)


DEFAULT_FRESHNESS_RULES = (
    FreshnessRule("market", GOLD_FUTURES, "COMEX黄金期货", 3),
    FreshnessRule("market", DOLLAR_INDEX, "美元指数", 3),
    FreshnessRule("market", USD_CNY, "USD/CNY", 3),
    FreshnessRule("market", SGE_AU9999, "上金所 Au99.99", 3),
    FreshnessRule("macro", "DFII10", "美国10年期实际利率", 4),
    FreshnessRule("macro", "DGS10", "美国10年期名义利率", 4),
    FreshnessRule("macro", "CPIAUCSL", "美国CPI", 45),
    FreshnessRule("macro", "PCEPILFE", "美国核心PCE", 45),
)


def evaluate_freshness(
    rule: FreshnessRule,
    latest_date: str | None,
    as_of: date | None = None,
) -> FreshnessResult:
    if not latest_date:
        return FreshnessResult(
            dataset_type=rule.dataset_type,
            code=rule.code,
            label=rule.label,
            latest_date=None,
            age_days=None,
            max_age_days=rule.max_age_days,
            status="missing",
        )

    as_of = as_of or date.today()
    data_date = date.fromisoformat(latest_date)
    age_days = max(0, (as_of - data_date).days)
    status = "fresh" if age_days <= rule.max_age_days else "stale"
    return FreshnessResult(
        dataset_type=rule.dataset_type,
        code=rule.code,
        label=rule.label,
        latest_date=latest_date,
        age_days=age_days,
        max_age_days=rule.max_age_days,
        status=status,
    )


def collect_freshness(
    rules=DEFAULT_FRESHNESS_RULES,
    as_of: date | None = None,
    session_factory=SessionLocal,
):
    results = []
    with session_factory() as session:
        for rule in rules:
            if rule.dataset_type == "market":
                latest_date = session.scalar(
                    select(func.max(MarketQuote.date)).where(
                        MarketQuote.symbol == rule.code
                    )
                )
            elif rule.dataset_type == "macro":
                latest_date = session.scalar(
                    select(func.max(MacroIndicator.date)).where(
                        MacroIndicator.series_id == rule.code
                    )
                )
            else:
                raise ValueError(f"不支持的数据类型：{rule.dataset_type}")
            results.append(evaluate_freshness(rule, latest_date, as_of))
    return results
