#!/usr/bin/env python3
"""build_tradable_flags 的 SQL 行为测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import build_tradable_flags as mod
import duckdb
import pytest
from quant_schema.market_ddl import FACTOR_TABLES, WAREHOUSE_TABLES


@pytest.fixture()
def con(tmp_path: Path):
    connection = duckdb.connect(str(tmp_path / "market.duckdb"))
    for table in WAREHOUSE_TABLES + FACTOR_TABLES:
        connection.execute(table.ddl())
    connection.execute(
        "INSERT INTO fact_daily (ts_code, trade_date, close, vol) VALUES "
        "('A', DATE '2024-01-02', 10, 100), "
        "('A', DATE '2024-01-03', 10, 0), "
        "('A', DATE '2024-01-04', 11, 100)"
    )
    connection.execute(
        "INSERT INTO fact_stk_limit (ts_code, trade_date, up_limit, down_limit) VALUES "
        "('A', DATE '2024-01-02', 11, 9), "
        "('A', DATE '2024-01-03', 11, 9), "
        "('A', DATE '2024-01-04', 11, 9)"
    )
    connection.execute(
        "INSERT INTO dim_stock_basic (ts_code, list_status, list_date) "
        "VALUES ('A', 'L', DATE '2024-01-01')"
    )
    try:
        yield connection
    finally:
        connection.close()


def test_dry_run_does_not_write(con) -> None:
    stats = mod.build_flags(con, date(2024, 1, 2), date(2024, 1, 4), apply=False)
    assert stats == {"rows": 3, "codes": 1, "applied": False}
    assert con.execute("SELECT count(*) FROM fact_tradable_flag").fetchone()[0] == 0


def test_apply_builds_flags(con) -> None:
    stats = mod.build_flags(con, date(2024, 1, 2), date(2024, 1, 4), apply=True)
    assert stats["written"] == 3

    rows = con.execute(
        "SELECT ts_code, trade_date, is_suspended, is_limit_up, is_limit_down, "
        "is_buyable, is_sellable, in_universe "
        "FROM fact_tradable_flag ORDER BY trade_date"
    ).fetchall()
    assert rows[0] == ("A", date(2024, 1, 2), False, False, False, True, True, True)
    # 停牌：不可买、不可卖
    assert rows[1] == ("A", date(2024, 1, 3), True, False, False, False, False, True)
    # 涨停：不可买、可卖
    assert rows[2] == ("A", date(2024, 1, 4), False, True, False, False, True, True)


def test_idempotent_apply(con) -> None:
    mod.build_flags(con, date(2024, 1, 2), date(2024, 1, 4), apply=True)
    mod.build_flags(con, date(2024, 1, 2), date(2024, 1, 4), apply=True)
    assert con.execute("SELECT count(*) FROM fact_tradable_flag").fetchone()[0] == 3
