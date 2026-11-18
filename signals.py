from dataclasses import asdict, dataclass
from datetime import timedelta

import pandas as pd

from analytics import imported_df, macro_df, quotes_df
from instruments import DOLLAR_INDEX, GOLD_FUTURES, SGE_AU9999, USD_CNY


RULE_VERSION = "0.1.0"


@dataclass(frozen=True)
class SignalResult:
    code: str
    label: str
    direction: str
    strength: int
    reason: str
    data_date: str | None
    data_status: str
    metrics: dict

    def to_dict(self):
        return asdict(self)


def real_yield_signal(frame: pd.DataFrame) -> SignalResult:
    if len(frame) < 21:
        return _unavailable("real_yield", "美国10年期实际利率", "至少需要21条数据")
    current = float(frame.iloc[-1]["value"])
    change = current - float(frame.iloc[-21]["value"])
    if change <= -0.15:
        direction, strength = "bullish", 1
        reason = f"实际利率20期下降 {abs(change):.2f} 个百分点，利好黄金"
    elif change >= 0.15:
        direction, strength = "bearish", -1
        reason = f"实际利率20期上升 {change:.2f} 个百分点，压制黄金"
    else:
        direction, strength = "neutral", 0
        reason = f"实际利率20期变化 {change:+.2f} 个百分点，未触发方向阈值"
    return SignalResult(
        "real_yield",
        "美国10年期实际利率",
        direction,
        strength,
        reason,
        str(frame.iloc[-1]["date"])[:10],
        "complete",
        {"current": round(current, 4), "change_20": round(change, 4)},
    )


def dollar_signal(frame: pd.DataFrame) -> SignalResult:
    if len(frame) < 60:
        return _unavailable("dollar", "美元指数", "至少需要60条数据")
    close = frame["close"].astype(float)
    current = float(close.iloc[-1])
    return_20 = (current / float(close.iloc[-21]) - 1) * 100
    ma60 = float(close.tail(60).mean())
    if return_20 <= -1.5 and current < ma60:
        direction, strength = "bullish", 1
        reason = f"美元指数20期下跌 {abs(return_20):.2f}% 且低于MA60，利好黄金"
    elif return_20 >= 1.5 and current > ma60:
        direction, strength = "bearish", -1
        reason = f"美元指数20期上涨 {return_20:.2f}% 且高于MA60，压制黄金"
    else:
        direction, strength = "neutral", 0
        reason = f"美元指数20期变化 {return_20:+.2f}%，未形成明确方向"
    return SignalResult(
        "dollar",
        "美元指数",
        direction,
        strength,
        reason,
        str(frame.iloc[-1]["date"])[:10],
        "complete",
        {"current": round(current, 4), "return_20_pct": round(return_20, 4), "ma60": round(ma60, 4)},
    )


def gold_trend_signal(frame: pd.DataFrame) -> SignalResult:
    if len(frame) < 200:
        return _unavailable("gold_trend", "黄金价格趋势", "至少需要200条数据")
    close = frame["close"].astype(float)
    current = float(close.iloc[-1])
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ma200 = close.rolling(200).mean()
    ma20_slope = float(ma20.iloc[-1] - ma20.iloc[-6])
    metrics = {
        "current": round(current, 4),
        "ma20": round(float(ma20.iloc[-1]), 4),
        "ma60": round(float(ma60.iloc[-1]), 4),
        "ma200": round(float(ma200.iloc[-1]), 4),
        "ma20_slope_5": round(ma20_slope, 4),
    }
    if current > ma20.iloc[-1] > ma60.iloc[-1] and current > ma200.iloc[-1] and ma20_slope > 0:
        direction, strength = "bullish", 1
        reason = "金价高于MA20、MA60和MA200，短期均线继续上行"
    elif current < ma20.iloc[-1] < ma60.iloc[-1] and current < ma200.iloc[-1] and ma20_slope < 0:
        direction, strength = "bearish", -1
        reason = "金价低于MA20、MA60和MA200，短期均线继续下行"
    else:
        direction, strength = "neutral", 0
        reason = "金价与长短期均线关系混合，趋势尚未确认"
    return SignalResult(
        "gold_trend",
        "黄金价格趋势",
        direction,
        strength,
        reason,
        str(frame.iloc[-1]["date"])[:10],
        "complete",
        metrics,
    )


def flow_signal(etf: pd.DataFrame, cot: pd.DataFrame) -> SignalResult:
    reasons = []
    directions = []
    metrics = {}
    dates = []
    if not etf.empty:
        recent = etf.groupby("date", as_index=False)["value1"].sum().tail(4)
        etf_flow = float(recent["value1"].sum())
        directions.append(1 if etf_flow > 0 else -1 if etf_flow < 0 else 0)
        reasons.append(f"黄金ETF最近四期净流量 {etf_flow:+.2f} 吨")
        metrics["etf_flow_4"] = round(etf_flow, 4)
        dates.append(str(recent.iloc[-1]["date"])[:10])
    if len(cot) >= 2:
        recent = cot.sort_values("date").tail(5)
        net = recent["value1"].astype(float) - recent["value2"].astype(float)
        cot_change = float(net.iloc[-1] - net.iloc[0])
        directions.append(1 if cot_change > 0 else -1 if cot_change < 0 else 0)
        reasons.append(f"COT管理基金净多头较对比期变化 {cot_change:+,.0f} 张")
        metrics["cot_net_change"] = round(cot_change, 4)
        dates.append(str(recent.iloc[-1]["date"])[:10])
    if not directions:
        return _unavailable("flows", "ETF与COT资金方向", "缺少ETF流量和COT持仓数据")
    total = sum(directions)
    direction = "bullish" if total > 0 else "bearish" if total < 0 else "neutral"
    strength = 1 if total > 0 else -1 if total < 0 else 0
    status = "complete" if len(directions) == 2 else "partial"
    if status == "partial":
        reasons.append("仅有一类资金数据，信号完整度降低")
    return SignalResult(
        "flows",
        "ETF与COT资金方向",
        direction,
        strength,
        "；".join(reasons),
        max(dates),
        status,
        metrics,
    )


def domestic_premium_signal(
    sge: pd.DataFrame,
    gold: pd.DataFrame,
    fx: pd.DataFrame,
) -> SignalResult:
    if sge.empty or gold.empty or fx.empty:
        return _unavailable("domestic_premium", "国内购买成本", "缺少Au99.99、国际黄金或汇率数据")
    domestic = _date_close(sge, "sge_close")
    international = _date_close(gold, "gold_close")
    exchange_rate = _date_close(fx, "fx_close")
    tolerance = timedelta(days=5)
    aligned = pd.merge_asof(domestic, international, on="date", direction="backward", tolerance=tolerance)
    aligned = pd.merge_asof(aligned, exchange_rate, on="date", direction="backward", tolerance=tolerance)
    aligned = aligned.dropna()
    if len(aligned) < 20:
        return _unavailable("domestic_premium", "国内购买成本", "至少需要20条可对齐行情")
    aligned["theoretical"] = aligned["gold_close"] * aligned["fx_close"] / 31.1034768
    aligned["premium_pct"] = (aligned["sge_close"] / aligned["theoretical"] - 1) * 100
    current = aligned.iloc[-1]
    percentile = float((aligned["premium_pct"] <= current["premium_pct"]).mean() * 100)
    premium = float(current["premium_pct"])
    if percentile <= 25:
        direction, strength = "bullish", 1
        reason = f"国内溢价 {premium:+.2f}%，处于样本 {percentile:.0f}% 分位，购买成本相对有利"
    elif percentile >= 90:
        direction, strength = "bearish", -1
        reason = f"国内溢价 {premium:+.2f}%，处于样本 {percentile:.0f}% 分位，购买成本偏高"
    else:
        direction, strength = "neutral", 0
        reason = f"国内溢价 {premium:+.2f}%，处于样本 {percentile:.0f}% 分位"
    return SignalResult(
        "domestic_premium",
        "国内购买成本",
        direction,
        strength,
        reason,
        current["date"].date().isoformat(),
        "complete",
        {
            "premium_pct": round(premium, 4),
            "premium_percentile": round(percentile, 2),
            "sample_size": len(aligned),
        },
    )


def build_core_signals() -> tuple[SignalResult, ...]:
    gold = quotes_df(GOLD_FUTURES)
    return (
        real_yield_signal(macro_df("DFII10")),
        dollar_signal(quotes_df(DOLLAR_INDEX)),
        gold_trend_signal(gold),
        flow_signal(imported_df("etf"), imported_df("cot")),
        domestic_premium_signal(
            quotes_df(SGE_AU9999),
            gold,
            quotes_df(USD_CNY),
        ),
    )


def _date_close(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    result = frame[["date", "close"]].copy()
    result["date"] = pd.to_datetime(result["date"])
    result[name] = result.pop("close").astype(float)
    return result.sort_values("date")


def _unavailable(code: str, label: str, reason: str) -> SignalResult:
    return SignalResult(code, label, "unavailable", 0, reason, None, "missing", {})
