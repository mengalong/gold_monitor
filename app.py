import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import select
from database import init_db, SessionLocal, CollectionLog, ScoreRecord
from analytics import quotes_df, macro_df, imported_df, calculate_domestic_theoretical
from indicators import add_technical_indicators
from collectors import run_daily_update
from reporting import generate_weekly_report
from config import REPORTS_DIR, validate_settings
from instruments import DOLLAR_INDEX, GOLD_FUTURES, SGE_AU9999, USD_CNY
from data_quality import assess_core_data_quality, collect_freshness
from portfolio import PortfolioContext, latest_portfolio, save_portfolio

st.set_page_config(page_title="Gold Monitor", page_icon="🟡", layout="wide")
setting_errors = validate_settings()
if setting_errors:
    for error in setting_errors:
        st.error(error)
    st.stop()
init_db()

st.title("🟡 Gold Monitor")
st.caption("黄金市场持续监测系统 · MVP · Python 3.12 / SQLite")

with st.sidebar:
    st.header("控制面板")
    if st.button("立即更新行情与宏观数据", use_container_width=True):
        with st.spinner("正在采集数据……"):
            result = run_daily_update()
        st.success("采集任务已执行")
        for k, v in result.items():
            st.write(f"**{k}**：{v}")
        st.rerun()
    if st.button("生成本周分析报告", use_container_width=True):
        report = generate_weekly_report()
        path = REPORTS_DIR / "latest_weekly_report.md"
        path.write_text(report, encoding="utf-8")
        st.success(f"报告已生成：{path.name}")
        st.download_button("下载周报 Markdown", report, file_name="gold_weekly_report.md")

tabs = st.tabs(["市场总览", "宏观经济", "技术分析", "国内金价", "数据管理"])

with tabs[0]:
    gold = quotes_df(GOLD_FUTURES)
    dxy = quotes_df(DOLLAR_INDEX)
    real = macro_df("DFII10")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("黄金期货代理价格", f"{gold.iloc[-1]['close']:,.2f}" if not gold.empty else "暂无数据",
              f"{gold.iloc[-1]['date']}" if not gold.empty else None)
    c2.metric("美元指数", f"{dxy.iloc[-1]['close']:.2f}" if not dxy.empty else "暂无数据",
              f"{dxy.iloc[-1]['date']}" if not dxy.empty else None)
    c3.metric("美国10年期实际利率", f"{real.iloc[-1]['value']:.2f}%" if not real.empty else "暂无数据",
              f"{real.iloc[-1]['date']}" if not real.empty else None)
    usdcny = quotes_df(USD_CNY)
    c4.metric("USD/CNY参考行情", f"{usdcny.iloc[-1]['close']:.4f}" if not usdcny.empty else "暂无数据",
              f"{usdcny.iloc[-1]['date']}" if not usdcny.empty else None)
    if not gold.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=gold["date"], y=gold["close"], name="GC=F", line=dict(color="#D6A43B")))
        fig.update_layout(title="国际黄金代理行情（COMEX GC=F）", xaxis_title="", yaxis_title="USD / troy oz", height=420)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("尚无行情数据。点击左侧“立即更新行情与宏观数据”，或先配置数据源。")
    st.caption("注意：GC=F是COMEX黄金期货代理行情，并非现货XAU/USD。免费行情可能延迟。")

with tabs[1]:
    st.subheader("宏观经济")
    for series, label in [("DFII10","美国10年期实际利率"),("DGS10","美国10年期名义利率"),("CPIAUCSL","美国CPI指数"),("PCEPILFE","核心PCE价格指数")]:
        df = macro_df(series)
        with st.expander(label, expanded=(series=="DFII10")):
            if df.empty:
                st.info("暂无数据。配置FRED_API_KEY后点击更新。")
            else:
                fig = go.Figure(go.Scatter(x=df["date"], y=df["value"], name=series))
                fig.update_layout(height=300, yaxis_title=df.iloc[-1]["units"])
                st.plotly_chart(fig, use_container_width=True)
                st.caption(f"最新数据日期：{df.iloc[-1]['date']}")

with tabs[2]:
    st.subheader("技术分析")
    if not gold.empty:
        tech = add_technical_indicators(gold)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=tech["date"], y=tech["close"], name="黄金"))
        for col in ["ma20","ma60","ma120","ma250"]:
            fig.add_trace(go.Scatter(x=tech["date"], y=tech[col], name=col.upper()))
        fig.update_layout(height=480, yaxis_title="USD / troy oz")
        st.plotly_chart(fig, use_container_width=True)
        last = tech.iloc[-1]
        a,b,c = st.columns(3)
        a.metric("RSI(14)", f"{last['rsi14']:.1f}" if pd.notna(last["rsi14"]) else "样本不足")
        b.metric("MACD", f"{last['macd']:.2f}" if pd.notna(last["macd"]) else "样本不足")
        c.metric("近20日涨跌幅", f"{last['return_20d']:.2f}%" if pd.notna(last["return_20d"]) else "样本不足")
        st.dataframe(tech.tail(20), use_container_width=True, hide_index=True)
    else:
        st.info("暂无黄金行情数据。")

with tabs[3]:
    st.subheader("国内黄金价格")
    st.write("国内理论价 = 国际金价 × USD/CNY ÷ 31.1034768")
    gold = quotes_df(GOLD_FUTURES)
    fx = quotes_df(USD_CNY)
    sge = quotes_df(SGE_AU9999)
    domestic = imported_df("au9999")
    if not gold.empty and not fx.empty:
        g, f = gold.iloc[-1], fx.iloc[-1]
        theory = calculate_domestic_theoretical(float(g["close"]), float(f["close"]))
        st.metric("国内理论金价（参考）", f"¥{theory:,.2f}/克")
        st.caption(f"国际行情日期：{g['date']}；汇率日期：{f['date']}。两者日期可能不一致。")
        if not sge.empty:
            actual = float(sge.iloc[-1]["close"])
            st.metric("上金所 Au99.99", f"¥{actual:,.2f}/克", f"溢价 ¥{actual-theory:,.2f}/克")
            st.caption(f"Au99.99 行情日期：{sge.iloc[-1]['date']}；来源：上海黄金交易所。")
        elif not domestic.empty:
            actual = domestic.iloc[-1]["value1"]
            st.metric("Au99.99导入价格", f"¥{actual:,.2f}/克", f"溢价 ¥{actual-theory:,.2f}/克")
    else:
        st.info("需要先有国际黄金与USD/CNY行情。Au99.99可在数据管理页导入。")
    if not domestic.empty:
        st.dataframe(domestic.rename(columns={"value1":"close_CNY_g"}), use_container_width=True, hide_index=True)
    if not sge.empty:
        st.dataframe(sge.tail(60), use_container_width=True, hide_index=True)

with tabs[4]:
    st.subheader("数据导入与采集日志")
    st.markdown("#### 个人黄金配置")
    saved_portfolio = latest_portfolio()
    with st.form("portfolio_form"):
        p1, p2 = st.columns(2)
        total_assets = p1.number_input(
            "金融资产总额（元）",
            min_value=0.0,
            value=float(saved_portfolio.total_assets if saved_portfolio else 0),
            step=10_000.0,
        )
        current_gold = p2.number_input(
            "当前黄金市值（元）",
            min_value=0.0,
            value=float(saved_portfolio.current_gold_value if saved_portfolio else 0),
            step=1_000.0,
        )
        max_allocation_pct = p1.number_input(
            "黄金配置上限（%）",
            min_value=0.1,
            max_value=100.0,
            value=float(saved_portfolio.max_gold_allocation * 100 if saved_portfolio else 15.0),
            step=0.5,
        )
        remaining_budget = p2.number_input(
            "剩余黄金预算（元）",
            min_value=0.0,
            value=float(saved_portfolio.remaining_budget if saved_portfolio else 0),
            step=1_000.0,
        )
        if st.form_submit_button("保存今日持仓快照"):
            context = PortfolioContext(
                total_assets=total_assets,
                current_gold_value=current_gold,
                max_gold_allocation=max_allocation_pct / 100,
                remaining_budget=remaining_budget,
            )
            errors = context.validate()
            if errors:
                for error in errors:
                    st.error(error)
            else:
                save_portfolio(context)
                st.success("今日持仓快照已保存")
                st.rerun()
    if saved_portfolio:
        st.caption(
            f"当前黄金占比 {saved_portfolio.current_allocation:.2%}；"
            f"距配置上限仍可增加 ¥{saved_portfolio.allocation_headroom:,.0f}。"
        )
    quality = assess_core_data_quality()
    freshness = collect_freshness()
    freshness_labels = {"fresh": "正常", "stale": "过期", "missing": "缺失"}
    if quality.ready:
        st.success(f"核心数据质量门：通过（检查通过率 {quality.confidence:.1f}%）")
    else:
        st.error(f"核心数据质量门：未通过（检查通过率 {quality.confidence:.1f}%）")
        with st.expander("查看阻断原因", expanded=True):
            for blocker in quality.blockers:
                st.write(f"- {blocker}")
    st.markdown("#### 数据新鲜度")
    st.dataframe(
        [
            {
                "数据": item.label,
                "代码": item.code,
                "最新日期": item.latest_date or "—",
                "距今天数": item.age_days if item.age_days is not None else "—",
                "允许天数": item.max_age_days,
                "状态": freshness_labels[item.status],
            }
            for item in freshness
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("#### 历史覆盖度")
    st.dataframe(
        [
            {
                "数据": item.label,
                "观察窗口（天）": item.window_days,
                "已有条数": item.available_points,
                "最低条数": item.minimum_points,
                "状态": "充足" if item.status == "sufficient" else "不足",
            }
            for item in quality.coverage
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("CSV格式说明见项目 README。")
    dataset = st.selectbox("导入数据类型", ["au9999", "etf", "cot", "central_bank"])
    uploaded = st.file_uploader("选择CSV文件", type=["csv"])
    if uploaded is not None and st.button("导入CSV"):
        df = pd.read_csv(uploaded)
        required = {
            "au9999": ["date","close"],
            "etf": ["date","region","flow_tonnes","holdings_tonnes"],
            "cot": ["report_date","managed_money_long","managed_money_short","open_interest"],
            "central_bank": ["date","country","gold_tonnes","change_tonnes"],
        }[dataset]
        missing = [c for c in required if c not in df.columns]
        if missing:
            st.error(f"缺少必要列：{missing}")
        else:
            from database import ImportedDatum
            with SessionLocal() as s:
                for _, row in df.iterrows():
                    d = str(row["report_date"] if dataset=="cot" else row["date"])[:10]
                    key = str(row.get("region", row.get("country", "")))
                    if dataset=="au9999":
                        vals = (float(row["close"]), None, None, None)
                    elif dataset=="etf":
                        vals = (float(row["flow_tonnes"]), float(row["holdings_tonnes"]), None, None)
                    elif dataset=="cot":
                        vals = (float(row["managed_money_long"]), float(row["managed_money_short"]), float(row["open_interest"]), None)
                    else:
                        vals = (float(row["gold_tonnes"]), float(row["change_tonnes"]), None, None)
                    obj = s.scalar(select(ImportedDatum).where(ImportedDatum.dataset==dataset, ImportedDatum.date==d, ImportedDatum.key==key))
                    if obj:
                        obj.value1,obj.value2,obj.value3,obj.value4 = vals
                    else:
                        s.add(ImportedDatum(dataset=dataset,date=d,key=key,value1=vals[0],value2=vals[1],value3=vals[2],value4=vals[3]))
                s.commit()
            st.success(f"导入完成：{len(df)}行")
    with SessionLocal() as s:
        logs = s.scalars(select(CollectionLog).order_by(CollectionLog.created_at.desc()).limit(30)).all()
        if logs:
            st.dataframe([{"时间":x.created_at,"任务":x.task,"状态":x.status,"信息":x.message} for x in logs], use_container_width=True, hide_index=True)
