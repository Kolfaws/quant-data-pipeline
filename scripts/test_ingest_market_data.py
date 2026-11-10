#!/usr/bin/env python3
"""ingest_market_data._ingest_stock 的分表降级测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb
import ingest_market_data as ingest
import polars as pl
import pytest
from quant_schema.market_ddl import WAREHOUSE_TABLES

from data_pipeline.core.errors import FetchError


@pytest.fixture()
def con(tmp_path: Path):
    connection = duckdb.connect(str(tmp_path / "market.duckdb"))
    for table in WAREHOUSE_TABLES:
        connection.execute(table.ddl())
    try:
        yield connection
    finally:
        connection.close()


class _Source:
    def __init__(self, *, adj_fails: bool = False, limit_fails: bool = False) -> None:
        self.adj_fails = adj_fails
        self.limit_fails = limit_fails
        self.calls: list[str] = []

    def fetch_daily(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        self.calls.append("daily")
        return pl.DataFrame(
            {
                "ts_code": [ts_code],
                "trade_date": [date(2024, 1, 2)],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.5],
                "pre_close": [10.0],
                "chg": [0.5],
                "pct_chg": [5.0],
                "vol": [100.0],
                "amount": [1050.0],
            }
        )

    def fetch_adj_factor(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        self.calls.append("adj_factor")
        if self.adj_fails:
            raise FetchError("adj_factor 频率超限")
        return pl.DataFrame(
            {
                "ts_code": [ts_code],
                "trade_date": [date(2024, 1, 2)],
                "adj_factor": [1.0],
            }
        )

    def fetch_daily_basic(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        self.calls.append("daily_basic")
        return pl.DataFrame(
            {
                "ts_code": [ts_code],
                "trade_date": [date(2024, 1, 2)],
                "turnover_rate": [1.2],
                "total_mv": [1000.0],
            }
        )

    def fetch_stk_limit(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        self.calls.append("stk_limit")
        if self.limit_fails:
            raise FetchError("stk_limit 无权限")
        return pl.DataFrame(
            {
                "ts_code": [ts_code],
                "trade_date": [date(2024, 1, 2)],
                "pre_close": [10.0],
                "up_limit": [11.0],
                "down_limit": [9.0],
            }
        )


def _args() -> SimpleNamespace:
    return SimpleNamespace(
        start="2024-01-01",
        end="2024-01-02",
        start_compact="20240101",
        end_compact="20240102",
        daily_basic="all",
        stk_limit="all",
    )


def _log_rows(con) -> dict[str, tuple[int, str]]:
    return {
        str(row[0]): (int(row[1]), str(row[2]))
        for row in con.execute(
            "SELECT table_name, row_count, status FROM meta_ingest_log"
        ).fetchall()
    }


def test_adj_failure_does_not_block_daily_or_other_tables(con) -> None:
    source = _Source(adj_fails=True)
    ingest._ingest_stock(con, source, "600000.SH", _args())

    assert con.execute("SELECT count(*) FROM fact_daily").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM fact_daily_basic").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM fact_stk_limit").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM fact_adj_factor").fetchone()[0] == 0
    logs = _log_rows(con)
    assert logs["fact_daily"] == (1, "ok")
    assert logs["fact_adj_factor"] == (0, "failed")
    assert logs["fact_daily_basic"] == (1, "ok")
    assert logs["fact_stk_limit"] == (1, "ok")


def test_daily_failure_skips_remaining_tables(con) -> None:
    class _Broken(_Source):
        def fetch_daily(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
            raise FetchError("daily 无权限")

    source = _Broken()
    ingest._ingest_stock(con, source, "600000.SH", _args())

    assert con.execute("SELECT count(*) FROM fact_daily").fetchone()[0] == 0
    assert "adj_factor" not in source.calls
    logs = _log_rows(con)
    assert logs["fact_daily"] == (0, "failed")


def test_stk_limit_failure_is_isolated(con) -> None:
    source = _Source(limit_fails=True)
    ingest._ingest_stock(con, source, "600000.SH", _args())

    assert con.execute("SELECT count(*) FROM fact_daily").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM fact_stk_limit").fetchone()[0] == 0
    logs = _log_rows(con)
    assert logs["fact_daily"] == (1, "ok")
    assert logs["fact_stk_limit"] == (0, "failed")


def test_stk_limit_can_be_skipped(con) -> None:
    source = _Source()
    args = _args()
    args.stk_limit = "none"
    ingest._ingest_stock(con, source, "600000.SH", args)

    assert "stk_limit" not in source.calls
    assert "fact_stk_limit" not in _log_rows(con)
