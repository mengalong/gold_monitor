import re
from datetime import date, timedelta
from html.parser import HTMLParser

import pandas as pd
import requests

from market_data import MarketDataResult


SGE_DAILY_URL = "https://www.sge.com.cn/sjzx/quotation_daily_new"
SGE_SOURCE = "上海黄金交易所（官方每日行情）"
SGE_CONTRACT = "Au99.99"
_COLUMNS = ("date", "open", "high", "low", "close", "volume")


class SGEDataError(RuntimeError):
    pass


class _DailyTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_daily_table = False
        self.in_row = False
        self.in_cell = False
        self.cell_parts = []
        self.current_row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "table" and "daily_new_table" in attributes.get("class", "").split():
            self.in_daily_table = True
        elif self.in_daily_table and tag == "tr":
            self.in_row = True
            self.current_row = []
        elif self.in_row and tag in {"td", "th"}:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data):
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag):
        if self.in_cell and tag in {"td", "th"}:
            self.current_row.append("".join(self.cell_parts).strip())
            self.in_cell = False
        elif self.in_row and tag == "tr":
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_row = False
        elif self.in_daily_table and tag == "table":
            self.in_daily_table = False


def _number(value):
    value = value.replace(",", "").strip()
    if not value or value == "-":
        return None
    return float(value)


def parse_sge_daily_html(html, contract=SGE_CONTRACT):
    parser = _DailyTableParser()
    parser.feed(html)
    expected_header = ["日期", "合约", "开盘价", "最高价", "最低价", "收盘价"]
    if not parser.rows or parser.rows[0][:6] != expected_header:
        raise SGEDataError("上金所每日行情页面结构不符合预期")

    records = []
    for row in parser.rows[1:]:
        if len(row) < 10 or row[1] != contract:
            continue
        try:
            date.fromisoformat(row[0])
            record = {
                "date": row[0],
                "open": _number(row[2]),
                "high": _number(row[3]),
                "low": _number(row[4]),
                "close": _number(row[5]),
                "volume": _number(row[9]),
            }
        except (TypeError, ValueError) as exc:
            raise SGEDataError(f"上金所每日行情包含无效字段：{row[:10]}") from exc
        if record["close"] is not None:
            records.append(record)
    return pd.DataFrame(records, columns=_COLUMNS)


def _last_page(html):
    pages = [
        int(value)
        for value in re.findall(r"gotoPage\([^)]*,\s*['\"](\d+)['\"]\)", html)
    ]
    return max(pages, default=1)


def _date_chunks(start_date, end_date):
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=30), end_date)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def fetch_sge_daily(start_date, end_date, http_get=requests.get):
    if start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")

    frames = []
    for chunk_start, chunk_end in _date_chunks(start_date, end_date):
        params = {
            "start_date": chunk_start.isoformat(),
            "end_date": chunk_end.isoformat(),
            "inst_ids": SGE_CONTRACT,
        }
        response = http_get(
            SGE_DAILY_URL,
            params=params,
            timeout=30,
            headers={"User-Agent": "GoldMonitor/1.0"},
        )
        response.raise_for_status()
        first_html = response.text
        frames.append(parse_sge_daily_html(first_html))
        for page in range(2, _last_page(first_html) + 1):
            page_response = http_get(
                SGE_DAILY_URL,
                params={**params, "p": page},
                timeout=30,
                headers={"User-Agent": "GoldMonitor/1.0"},
            )
            page_response.raise_for_status()
            frames.append(parse_sge_daily_html(page_response.text))

    available = [frame for frame in frames if not frame.empty]
    if not available:
        raise SGEDataError(f"上金所未返回 {SGE_CONTRACT} 行情")
    combined = pd.concat(available, ignore_index=True)
    combined = combined.drop_duplicates(subset=["date"], keep="last")
    combined = combined.sort_values("date").reset_index(drop=True)
    return MarketDataResult(frame=combined, source=SGE_SOURCE)
