from datetime import date, timedelta
from analytics import quotes_df, macro_df, imported_df
from indicators import add_technical_indicators
from instruments import DOLLAR_INDEX, GOLD_FUTURES

def _latest_change(df, value_col="close", periods=5):
    if df.empty:
        return None
    vals = df[value_col].dropna()
    if len(vals) <= periods:
        return None
    return (vals.iloc[-1] / vals.iloc[-periods-1] - 1) * 100

def generate_weekly_report():
    end = date.today()
    start = end - timedelta(days=7)
    gold = quotes_df(GOLD_FUTURES)
    dxy = quotes_df(DOLLAR_INDEX)
    real = macro_df("DFII10")
    lines = [
        f"# 黄金市场周报（{start.isoformat()} 至 {end.isoformat()}）",
        "",
        "> 自动生成的第一版数据摘要。行情和宏观数据的最新日期可能不同；本报告不构成投资建议。",
        "",
        "## 一、本周市场表现",
    ]
    if not gold.empty:
        lines += [f"- 国际黄金代理行情（GC=F）最新收盘：{gold.iloc[-1]['close']:.2f} 美元/盎司（数据日期：{gold.iloc[-1]['date']}）。",
                  f"- 近5个交易日变化：{_latest_change(gold):.2f}%。" if _latest_change(gold) is not None else "- 国际黄金历史样本不足，无法计算周度变化。"]
    else:
        lines.append("- 暂无国际黄金行情数据。")
    if not dxy.empty:
        lines.append(f"- 美元指数最新值：{dxy.iloc[-1]['close']:.3f}（数据日期：{dxy.iloc[-1]['date']}）。")
    if not real.empty:
        lines.append(f"- 美国10年期实际利率最新值：{real.iloc[-1]['value']:.3f}%（数据日期：{real.iloc[-1]['date']}）。")
    lines += ["", "## 二、资金流向", "- 第一版尚未自动接入WGC ETF与央行购金数据。请在数据管理页面导入官方CSV后纳入分析。",
              "", "## 三、技术面", "- 请在技术分析页面查看均线、RSI、MACD和波动率指标。",
              "", "## 四、国内黄金市场", "- 请导入Au99.99 CSV，并补充可靠的USD/CNY与国内行情数据后计算国内溢价。",
              "", "## 五、下周观察重点", "- 关注美国实际利率与美元指数方向。", "- 关注黄金ETF资金流和CFTC持仓报告是否出现持续性变化。",
              "", "## 六、数据质量说明", "- 本报告中的GC=F为COMEX黄金期货代理行情，不等同于现货XAU/USD。",
              "- ETF、COT、央行购金尚未接入时，不应将其视为已验证的资金面结论。"]
    return "\n".join(lines)
