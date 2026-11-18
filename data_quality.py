from dataclasses import asdict, dataclass
from datetime import date, timedelta

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


@dataclass(frozen=True)
class CoverageRule:
    dataset_type: str
    code: str
    label: str
    window_days: int
    minimum_points: int


@dataclass(frozen=True)
class CoverageResult:
    dataset_type: str
    code: str
    label: str
    window_days: int
    available_points: int
    minimum_points: int
    status: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DataQualityReport:
    as_of: str
    ready: bool
    confidence: float
    freshness: tuple[FreshnessResult, ...]
    coverage: tuple[CoverageResult, ...]
    blockers: tuple[str, ...]


DEFAULT_FRESHNESS_RULES = (
    FreshnessRule("market", GOLD_FUTURES, "COMEX黄金期货", 3),
    FreshnessRule("market", DOLLAR_INDEX, "美元指数", 3),
    FreshnessRule("market", USD_CNY, "USD/CNY", 9),
    FreshnessRule("market", SGE_AU9999, "上金所 Au99.99", 3),
    FreshnessRule("macro", "DFII10", "美国10年期实际利率", 4),
    FreshnessRule("macro", "DGS10", "美国10年期名义利率", 4),
    FreshnessRule("macro", "CPIAUCSL", "美国CPI", 45),
    FreshnessRule("macro", "PCEPILFE", "美国核心PCE", 45),
)

CORE_FRESHNESS_RULES = tuple(
    rule
    for rule in DEFAULT_FRESHNESS_RULES
    if rule.code in {GOLD_FUTURES, DOLLAR_INDEX, USD_CNY, SGE_AU9999, "DFII10"}
)

DEFAULT_COVERAGE_RULES = (
    CoverageRule("market", GOLD_FUTURES, "COMEX黄金期货", 400, 200),
    CoverageRule("market", DOLLAR_INDEX, "美元指数", 400, 200),
    CoverageRule("market", USD_CNY, "USD/CNY", 45, 20),
    CoverageRule("market", SGE_AU9999, "上金所 Au99.99", 90, 40),
    CoverageRule("macro", "DFII10", "美国10年期实际利率", 45, 20),
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


def collect_coverage(
    rules=DEFAULT_COVERAGE_RULES,
    as_of: date | None = None,
    session_factory=SessionLocal,
):
    as_of = as_of or date.today()
    results = []
    with session_factory() as session:
        for rule in rules:
            start_date = (as_of - timedelta(days=rule.window_days)).isoformat()
            if rule.dataset_type == "market":
                available = session.scalar(
                    select(func.count(MarketQuote.id)).where(
                        MarketQuote.symbol == rule.code,
                        MarketQuote.date >= start_date,
                        MarketQuote.date <= as_of.isoformat(),
                    )
                )
            elif rule.dataset_type == "macro":
                available = session.scalar(
                    select(func.count(MacroIndicator.id)).where(
                        MacroIndicator.series_id == rule.code,
                        MacroIndicator.date >= start_date,
                        MacroIndicator.date <= as_of.isoformat(),
                    )
                )
            else:
                raise ValueError(f"不支持的数据类型：{rule.dataset_type}")
            available = int(available or 0)
            results.append(
                CoverageResult(
                    dataset_type=rule.dataset_type,
                    code=rule.code,
                    label=rule.label,
                    window_days=rule.window_days,
                    available_points=available,
                    minimum_points=rule.minimum_points,
                    status="sufficient" if available >= rule.minimum_points else "insufficient",
                )
            )
    return results


def assess_core_data_quality(
    as_of: date | None = None,
    freshness_rules=CORE_FRESHNESS_RULES,
    coverage_rules=DEFAULT_COVERAGE_RULES,
    session_factory=SessionLocal,
):
    as_of = as_of or date.today()
    freshness = tuple(
        collect_freshness(freshness_rules, as_of=as_of, session_factory=session_factory)
    )
    coverage = tuple(
        collect_coverage(coverage_rules, as_of=as_of, session_factory=session_factory)
    )
    blockers = []
    passed = 0
    for item in freshness:
        if item.status == "fresh":
            passed += 1
        else:
            detail = "缺失" if item.status == "missing" else f"已过期 {item.age_days} 天"
            blockers.append(f"{item.label}数据{detail}")
    for item in coverage:
        if item.status == "sufficient":
            passed += 1
        else:
            blockers.append(
                f"{item.label}近 {item.window_days} 天仅有 {item.available_points} 条，"
                f"至少需要 {item.minimum_points} 条"
            )
    total_checks = len(freshness) + len(coverage)
    confidence = round(passed / total_checks * 100, 1) if total_checks else 0.0
    return DataQualityReport(
        as_of=as_of.isoformat(),
        ready=not blockers,
        confidence=confidence,
        freshness=freshness,
        coverage=coverage,
        blockers=tuple(blockers),
    )
