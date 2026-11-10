#!/usr/bin/env python3
"""schema 视图/表宏的语义测试：qfq/hfq、日收益、可交易过滤。"""

from __future__ import annotations

from pathlib import Path

import init_market_db as market
import pytest
from quant_schema.market_ddl import (
    FACTOR_STATIC_VIEWS,
    FACTOR_TABLES,
)


@pytest.fixture()
def con(tmp_path: Path):
    path = tmp_path / "market.duckdb"
    with market.database(path) as connection:
        market.init_schema(connection)
        for table in FACTOR_TABLES:
            connection.execute(table.ddl())
        connection.execute(
            f'CREATE OR REPLACE VIEW "v_factor_valid" AS '
            f"{FACTOR_STATIC_VIEWS['v_factor_valid']}"
        )
        connection.execute(
            "INSERT INTO fact_daily "
            "(ts_code, trade_date, open, high, low, close, pre_close, chg, pct_chg, vol, amount) "
            "VALUES ('A', DATE '2024-01-02', 10, 10, 10, 10, 10, 0, 5.0, 100, 1000), "
            "('A', DATE '2024-01-03', 5, 5, 5, 5, 5, 0, -2.5, 200, 1000)"
        )
        connection.execute(
            "INSERT INTO fact_adj_factor VALUES "
            "('A', DATE '2024-01-02', 1), ('A', DATE '2024-01-03', 2)"
        )
        try:
            yield connection
        finally:
            pass


def test_qfq_and_hfq_adjust_volume_and_keep_turnover(con) -> None:
    qfq = con.execute(
        "SELECT trade_date, close, vol, amount FROM v_daily_qfq ORDER BY trade_date"
    ).fetchall()
    # 1 拆 2：qfq 把历史价格减半、历史成交量翻倍，成交额保持真实值
    assert qfq[0][1] == pytest.approx(5.0)
    assert qfq[0][2] == pytest.approx(200.0)
    assert float(qfq[0][3]) == pytest.approx(1000.0)
    assert qfq[1][1] == pytest.approx(5.0)
    assert qfq[1][2] == pytest.approx(200.0)

    hfq = con.execute(
        "SELECT trade_date, close, vol, amount FROM v_daily_hfq ORDER BY trade_date"
    ).fetchall()
    # 后复权：历史价格不变、历史成交量减半
    assert hfq[0][1] == pytest.approx(10.0)
    assert hfq[0][2] == pytest.approx(100.0)
    assert float(hfq[0][3]) == pytest.approx(1000.0)
    assert hfq[1][1] == pytest.approx(10.0)
    assert hfq[1][2] == pytest.approx(100.0)


def test_qfq_daily_is_point_in_time(con) -> None:
    before = con.execute(
        "SELECT trade_date, close, vol FROM qfq_daily(DATE '2024-01-02') "
        "ORDER BY trade_date"
    ).fetchall()
    after = con.execute(
        "SELECT trade_date, close, vol FROM qfq_daily(DATE '2024-01-03') "
        "ORDER BY trade_date"
    ).fetchall()

    assert len(before) == 1
    assert before[0][1] == pytest.approx(10.0)
    assert before[0][2] == pytest.approx(100.0)
    # as-of 拆股日：历史价格/成交量按当日已知的最新因子重算
    assert len(after) == 2
    assert after[0][1] == pytest.approx(5.0)
    assert after[0][2] == pytest.approx(200.0)


def test_v_daily_return_uses_pct_chg(con) -> None:
    rows = con.execute(
        "SELECT trade_date, ret_1d FROM v_daily_return ORDER BY trade_date"
    ).fetchall()
    assert [row[1] for row in rows] == [pytest.approx(0.05), pytest.approx(-0.025)]


def test_factor_valid_excludes_stale(con) -> None:
    con.execute(
        "INSERT INTO fact_factor_daily "
        "(ts_code, trade_date, factor_id, value, is_stale) VALUES "
        "('A', DATE '2024-01-02', 1, 1.0, FALSE), "
        "('A', DATE '2024-01-03', 1, 2.0, TRUE)"
    )
    con.execute(
        "INSERT INTO fact_tradable_flag "
        "(ts_code, trade_date, is_suspended, is_st, is_limit_up, is_limit_down, "
        "is_buyable, is_sellable, in_universe) VALUES "
        "('A', DATE '2024-01-02', FALSE, FALSE, FALSE, FALSE, TRUE, TRUE, TRUE), "
        "('A', DATE '2024-01-03', FALSE, FALSE, FALSE, FALSE, TRUE, TRUE, TRUE)"
    )
    rows = con.execute(
        "SELECT trade_date, value FROM v_factor_valid ORDER BY trade_date"
    ).fetchall()
    assert rows == [(rows[0][0], 1.0)]


def test_data_health_warns_when_derived_tables_are_empty(con) -> None:
    con.execute("DELETE FROM fact_adj_factor")
    warnings = market.data_health_warnings(con)
    assert any("fact_adj_factor" in item for item in warnings)
    assert any("fact_tradable_flag" in item for item in warnings)
