import json
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import select

from data_quality import DataQualityReport, assess_core_data_quality
from database import AdviceRecord, SessionLocal, SignalSnapshot
from portfolio import PortfolioContext, latest_portfolio
from signals import RULE_VERSION, SignalResult, build_core_signals


@dataclass(frozen=True)
class AdviceResult:
    action: str
    suggested_amount: float
    budget_ratio: float
    confidence: float
    reasons: tuple[str, ...]
    opposing_factors: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    signal_counts: dict
    data_date: str | None
    rule_version: str
    blockers: tuple[str, ...]

    def to_dict(self):
        return asdict(self)


def generate_advice(
    signals: tuple[SignalResult, ...],
    quality: DataQualityReport,
    portfolio: PortfolioContext | None,
) -> AdviceResult:
    counts = {
        direction: sum(signal.direction == direction for signal in signals)
        for direction in ("bullish", "neutral", "bearish", "unavailable")
    }
    completeness = sum(
        1.0 if signal.data_status == "complete" else 0.5 if signal.data_status == "partial" else 0.0
        for signal in signals
    ) / len(signals) if signals else 0.0
    confidence = round(min(quality.confidence, completeness * 100), 1)
    blockers = list(quality.blockers)
    if not quality.ready and not blockers:
        blockers.append("核心数据质量门未通过")
    signal_by_code = {signal.code: signal for signal in signals}

    premium = signal_by_code.get("domestic_premium")
    if premium and premium.metrics.get("premium_percentile", 0) >= 90:
        blockers.append("国内溢价达到或超过历史90%分位")
    if counts["bearish"] >= 2:
        blockers.append(f"五个核心维度中有 {counts['bearish']} 个偏空")
    gold = signal_by_code.get("gold_trend")
    if gold and gold.direction == "bearish":
        blockers.append("金价低于关键均线且趋势继续下行")
    real_yield = signal_by_code.get("real_yield")
    dollar = signal_by_code.get("dollar")
    if real_yield and dollar and real_yield.direction == dollar.direction == "bearish":
        blockers.append("实际利率与美元指数同时快速上升")
    if portfolio and portfolio.allocation_headroom <= 0:
        blockers.append("当前黄金仓位已达到配置上限")

    action = "持有观察"
    ratio = 0.0
    amount = 0.0
    if blockers:
        action = "暂停加仓"
    elif counts["bullish"] >= 4 and confidence >= 80:
        action, ratio = "分批加仓", 0.20
    elif counts["bullish"] >= 3:
        action, ratio = "小额试探", 0.10

    if ratio > 0 and portfolio is None:
        action, ratio = "暂停加仓", 0.0
        blockers.append("尚未配置个人资产与黄金持仓，无法验证仓位上限")
    elif ratio > 0 and portfolio:
        amount = round(min(portfolio.remaining_budget * ratio, portfolio.allocation_headroom), 2)
        if amount <= 0:
            action, ratio = "暂停加仓", 0.0
            blockers.append("剩余预算或黄金配置空间为0")

    if action == "暂停加仓":
        reasons = tuple(blockers[:3])
        invalidation = ("所有否决条件解除", "至少三个核心维度转为偏多")
    elif action == "持有观察":
        reasons = tuple(
            signal.reason for signal in signals if signal.direction in {"neutral", "unavailable"}
        )[:3]
        invalidation = ("至少三个核心维度转为偏多", "出现两个以上偏空维度")
    else:
        reasons = tuple(signal.reason for signal in signals if signal.direction == "bullish")[:3]
        invalidation = (
            "数据质量门转为未通过",
            "偏空维度增加至两个",
            "国内溢价达到历史90%分位",
            "达到个人黄金配置上限",
        )
    opposing = tuple(
        signal.reason
        for signal in signals
        if signal.direction in {"bearish", "unavailable"}
    )[:3]
    dates = [signal.data_date for signal in signals if signal.data_date]
    return AdviceResult(
        action=action,
        suggested_amount=amount,
        budget_ratio=ratio,
        confidence=confidence,
        reasons=reasons,
        opposing_factors=opposing,
        invalidation_conditions=invalidation,
        signal_counts=counts,
        data_date=max(dates) if dates else None,
        rule_version=RULE_VERSION,
        blockers=tuple(blockers),
    )


def generate_current_advice():
    signals = build_core_signals()
    quality = assess_core_data_quality()
    return generate_advice(signals, quality, latest_portfolio()), signals, quality


def save_advice_snapshot(
    advice: AdviceResult,
    signals: tuple[SignalResult, ...],
    advice_date: date | None = None,
    session_factory=SessionLocal,
):
    date_key = (advice_date or date.today()).isoformat()
    with session_factory() as session:
        for signal in signals:
            row = session.scalar(
                select(SignalSnapshot).where(
                    SignalSnapshot.date == date_key,
                    SignalSnapshot.code == signal.code,
                )
            )
            values = {
                "direction": signal.direction,
                "strength": signal.strength,
                "reason": signal.reason,
                "data_date": signal.data_date,
                "data_status": signal.data_status,
                "metrics_json": json.dumps(signal.metrics, ensure_ascii=False),
                "rule_version": advice.rule_version,
            }
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                session.add(SignalSnapshot(date=date_key, code=signal.code, **values))

        record = session.scalar(select(AdviceRecord).where(AdviceRecord.date == date_key))
        values = {
            "action": advice.action,
            "suggested_amount": advice.suggested_amount,
            "budget_ratio": advice.budget_ratio,
            "confidence": advice.confidence,
            "reasons_json": json.dumps(advice.reasons, ensure_ascii=False),
            "opposing_factors_json": json.dumps(advice.opposing_factors, ensure_ascii=False),
            "invalidation_json": json.dumps(advice.invalidation_conditions, ensure_ascii=False),
            "signal_counts_json": json.dumps(advice.signal_counts, ensure_ascii=False),
            "data_date": advice.data_date,
            "rule_version": advice.rule_version,
        }
        if record:
            for key, value in values.items():
                setattr(record, key, value)
        else:
            session.add(AdviceRecord(date=date_key, **values))
        session.commit()


def refresh_and_save_advice():
    advice, signals, quality = generate_current_advice()
    save_advice_snapshot(advice, signals)
    return advice, signals, quality
