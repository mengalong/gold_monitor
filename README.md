# Gold Monitor（黄金市场持续监测系统）

第一版 MVP：Python 3.12 + Streamlit + SQLite + SQLAlchemy + Plotly。

## 项目文档

- [系统设计](docs/SYSTEM_DESIGN.md)
- [开发路线](docs/DEVELOPMENT_PLAN.md)

## 已实现
- 国际黄金（GC=F）行情采集：通过 Yahoo Finance/yfinance；数据可用性受第三方服务限制。
- 美元指数（DX-Y.NYB）行情采集（如数据源可用）。
- USD/CNY 汇率行情采集（CNY=X，作为参考行情，需与正式结算汇率区分）。
- FRED 宏观序列采集：DFII10、DGS10、CPIAUCSL、PCEPILFE；需要 FRED API Key。
- SQLite 原始行情、宏观数据、指标、评分、采集日志持久化。
- 技术指标：MA20/60/120/250、RSI14、MACD、布林带、ATR14。
- 国内理论金价换算、国内 Au99.99 CSV 导入、国内溢价计算。
- 首页总览、宏观、技术、国内金价、数据管理/导入页面。
- 周报 Markdown 生成（规则模板版，不依赖大模型 API）。

## 尚未实现/需要后续接入
- WGC ETF 流量、央行购金和 CFTC COT 的稳定自动采集。第一版先支持 CSV 导入，避免依赖不稳定网页抓取。
- 银行积存金报价自动采集。不同银行数据接口差异较大，建议后续确定具体银行后单独开发。
- 邮件/微信推送及 LLM 自动撰写周报。
- 历史评分模型回测和权重校准。

## 环境安装（Python 3.12）
建议使用 Conda：

```bash
conda create -n gold_monitor python=3.12 -y
conda activate gold_monitor
pip install -r requirements.txt
cp .env.example .env
```

在 https://fred.stlouisfed.org/docs/api/api_key.html 申请 FRED API Key，将其填入 `.env` 的 `FRED_API_KEY`。

## 启动

```bash
streamlit run app.py
```

首次启动会自动创建 `data/gold_monitor.db` 数据库。

## 测试

安装开发依赖并运行测试：

```bash
pip install -r requirements-dev.txt
pytest -q
```

每次推送和拉取请求都会通过 GitHub Actions 在 Python 3.12 环境执行语法检查和测试。

## 数据更新
在侧边栏点击“立即更新行情与宏观数据”。也可以执行一次性更新：

```bash
python run_update.py
```

如需自动定时运行（保持进程常驻）：

```bash
python scheduler.py
```

默认每天北京时间08:00更新行情与宏观数据，每周六09:00生成周报。请在服务器上使用 systemd、Docker restart policy 或其他进程管理方式保证 `scheduler.py` 持续运行。

注意：行情采集依赖 Yahoo Finance 第三方数据服务，可能存在延迟、缺失或接口变化。仪表盘会展示数据日期，不应将其视为交易所实时行情。

## 国内 Au99.99 / ETF / COT CSV 导入格式

### Au99.99
列名：`date, close`，可选 `open, high, low, volume`。日期格式建议 `YYYY-MM-DD`，价格单位人民币/克。

### ETF 流量
列名：`date, region, flow_tonnes, holdings_tonnes`。流量单位吨；同一日期可按区域多行。

### COT
列名：`report_date, managed_money_long, managed_money_short, open_interest`。单位为合约张数。

## 项目目录
```text
gold_monitor/
├── app.py
├── run_update.py
├── config.py
├── database.py
├── collectors.py
├── indicators.py
├── analytics.py
├── reporting.py
├── requirements.txt
├── .env.example
├── data/
├── reports/
└── pages/
```

## 数据解释原则
- 不同来源的日期/发布时间不同，必须区分行情日期与采集时间。
- FRED CPI/PCE 等月度指标是宏观统计序列，不是每日更新数据。
- ETF、央行购金、COT 存在发布滞后；CSV 导入时保留原始报告日期。
- 第一版综合评分是规则化研究指标，不是经历史回测验证的买卖信号。
