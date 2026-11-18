from datetime import date

import pytest

from sge_data import SGEDataError, SGE_SOURCE, fetch_sge_daily, parse_sge_daily_html


def _html(rows, last_page=1):
    body = "".join(
        f"""
        <tr>
          <td>{day}</td><td>{contract}</td><td>{open_price}</td>
          <td>{high}</td><td>{low}</td><td>{close}</td>
          <td>1.00</td><td>0.10%</td><td>{close}</td><td>{volume}</td>
          <td>1000</td><td>-</td><td></td><td></td>
        </tr>
        """
        for day, contract, open_price, high, low, close, volume in rows
    )
    pages = "".join(
        f"<li onclick=\"gotoPage('/daily?p=', '{page}')\">{page}</li>"
        for page in range(1, last_page + 1)
    )
    return f"""
    <html><table class="daily_new_table">
      <thead><tr>
        <th>日期</th><th>合约</th><th>开盘价</th><th>最高价</th>
        <th>最低价</th><th>收盘价</th><th>涨跌（元）</th><th>涨跌幅</th>
        <th>加权平均价</th><th>成交量（kg）</th><th>成交金额（元）</th>
        <th>市场持仓（手）</th><th>交收方向</th><th>交收量（手）</th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>{pages}</html>
    """


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_daily_table_is_parsed_and_other_contracts_are_ignored():
    html = _html(
        [
            ("2026-01-05", "Au99.99", "620.00", "625.00", "618.00", "623.50", "1,234.5"),
            ("2026-01-05", "Ag99.99", "15.00", "16.00", "14.00", "15.50", "100"),
        ]
    )

    result = parse_sge_daily_html(html)

    assert result.to_dict("records") == [
        {
            "date": "2026-01-05",
            "open": 620.0,
            "high": 625.0,
            "low": 618.0,
            "close": 623.5,
            "volume": 1234.5,
        }
    ]


def test_page_structure_change_is_reported_explicitly():
    with pytest.raises(SGEDataError, match="页面结构"):
        parse_sge_daily_html("<html><p>maintenance</p></html>")


def test_fetch_splits_long_ranges_and_reads_all_pages():
    calls = []

    def fake_get(url, params, **kwargs):
        calls.append(params.copy())
        if params["start_date"] == "2026-01-01" and params.get("p") == 2:
            return FakeResponse(
                _html([("2026-01-02", "Au99.99", "611", "613", "610", "612", "20")])
            )
        if params["start_date"] == "2026-01-01":
            return FakeResponse(
                _html([("2026-01-03", "Au99.99", "612", "614", "611", "613", "30")], last_page=2)
            )
        return FakeResponse(
            _html([("2026-02-02", "Au99.99", "614", "616", "613", "615", "40")])
        )

    result = fetch_sge_daily(date(2026, 1, 1), date(2026, 2, 5), http_get=fake_get)

    assert len(calls) == 3
    assert calls[0]["end_date"] == "2026-01-31"
    assert calls[1]["p"] == 2
    assert calls[2]["start_date"] == "2026-02-01"
    assert result.frame["date"].tolist() == ["2026-01-02", "2026-01-03", "2026-02-02"]
    assert result.source == SGE_SOURCE
