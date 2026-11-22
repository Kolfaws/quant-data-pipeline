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


# ---------------------------------------------------------------------------
# 整批事务：数据与 meta_ingest_log 同提交/回滚，失败留批次记录
# ---------------------------------------------------------------------------
class _RunSource:
    """覆盖 run_ingest 全流程的假数据源（不触网）。"""

    def __init__(
        self,
        *,
        bad_daily_on: str | None = None,
        interrupt_on: str | None = None,
        adj_fails: bool = False,
    ) -> None:
        self.bad_daily_on = bad_daily_on
        self.interrupt_on = interrupt_on
        self.adj_fails = adj_fails

    def fetch_trade_cal(self, start: str, end: str, calendar: str) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_stock_basic(self) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_daily(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        if self.interrupt_on == ts_code:
            raise KeyboardInterrupt("模拟中断")
        if self.bad_daily_on == ts_code:
            # 字符串日期写入 DATE 列会触发 duckdb.ConversionException
            return pl.DataFrame(
                {"ts_code": [ts_code], "trade_date": ["bad-date"], "close": [1.0]}
            )
        return pl.DataFrame(
            {
                "ts_code": [ts_code],
                "trade_date": [date(2010, 1, 4)],
                "close": [10.0],
            }
        )

    def fetch_adj_factor(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        if self.adj_fails:
            raise FetchError("adj_factor 频率超限")
        return pl.DataFrame()

    def fetch_daily_basic(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_stk_limit(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_index_daily(self, code: str, start: str, end: str) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_fund_daily(self, code: str, start: str, end: str) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_index_weight(self, code: str, compact: str) -> pl.DataFrame:
        return pl.DataFrame()


def _run_args(**overrides) -> SimpleNamespace:
    base = {
        "start": "2010-01-01",
        "end": "2010-12-31",
        "start_compact": "20100101",
        "end_compact": "20101231",
        "calendar": "SSE",
        "stocks": ("600000.SH", "600001.SH"),
        "indexes": (),
        "funds": (),
        "daily_basic": "none",
        "stk_limit": "none",
        "with_index_weight": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _log_entries(con) -> dict[str, tuple[str, str | None]]:
    return {
        str(row[0]): (str(row[1]), None if row[2] is None else str(row[2]))
        for row in con.execute(
            "SELECT table_name, status, detail FROM meta_ingest_log"
        ).fetchall()
    }


def _count(con, table: str) -> int:
    return int(con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])


def test_run_ingest_commits_data_and_logs_in_one_transaction(con) -> None:
    args = _run_args()
    batch = ingest.run_ingest(con, _RunSource(), args)

    assert batch.row_count == 2
    assert args.batch is batch
    assert _count(con, "fact_daily") == 2
    logs = _log_entries(con)
    assert logs["ingest_batch"][0] == "ok"
    assert batch.batch_id in (logs["ingest_batch"][1] or "")
    assert batch.batch_id in (logs["fact_daily"][1] or "")


def test_run_ingest_rolls_back_on_duckdb_error_and_logs_failed(con) -> None:
    args = _run_args()
    with pytest.raises(duckdb.Error):
        ingest.run_ingest(con, _RunSource(bad_daily_on="600001.SH"), args)

    # 第一只股票已写入也被回滚，不留“部分表已写”的状态
    assert _count(con, "fact_daily") == 0
    rows = con.execute(
        "SELECT table_name, status, detail FROM meta_ingest_log"
    ).fetchall()
    assert len(rows) == 1, rows
    table_name, status, detail = rows[0]
    assert table_name == ingest.BATCH_TABLE
    assert status == "failed"
    assert args.batch.batch_id in str(detail)
    assert "ConversionException" in str(detail)


def test_run_ingest_rolls_back_and_logs_on_interrupt(con) -> None:
    args = _run_args()
    with pytest.raises(KeyboardInterrupt):
        ingest.run_ingest(con, _RunSource(interrupt_on="600001.SH"), args)

    assert _count(con, "fact_daily") == 0
    rows = con.execute(
        "SELECT table_name, status, detail FROM meta_ingest_log"
    ).fetchall()
    assert len(rows) == 1, rows
    assert rows[0][0] == ingest.BATCH_TABLE
    assert rows[0][1] == "failed"
    assert args.batch.batch_id in str(rows[0][2])
    assert "KeyboardInterrupt" in str(rows[0][2])


def test_run_ingest_soft_fetch_failure_commits_other_tables(con) -> None:
    args = _run_args()
    ingest.run_ingest(con, _RunSource(adj_fails=True), args)

    assert _count(con, "fact_daily") == 2
    logs = _log_entries(con)
    assert logs["fact_daily"][0] == "ok"
    assert logs["fact_adj_factor"][0] == "failed"
    assert logs["ingest_batch"][0] == "ok"
