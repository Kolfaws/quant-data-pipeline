#!/usr/bin/env python3
"""build_tradable_flags.py — 从行情 + 涨跌停 + 股票列表派生每日可交易标记。

规则（与 docs/init_factor_db.md 一致）：

    is_suspended  = vol IS NULL OR vol = 0
    is_limit_up   = close >= up_limit    AND trade_date > list_date
    is_limit_down = close <= down_limit  AND trade_date > list_date
    in_universe   = list_date <= trade_date < delist_date（缺股票列表时退化为 True）
    is_buyable    = NOT suspended AND NOT limit_up AND in_universe
    is_sellable   = NOT suspended AND NOT limit_down AND in_universe

``list_date`` 当日不应用涨跌停：A 股 IPO 首日通常不设涨跌幅限制，
Tushare 的 ``stk_limit`` 在该日可能给出参考价，直接比较会把首日误判为涨跌停。

已知限制：``dim_stock_basic`` 只有当前快照，没有日频 ST 标记，
因此 ``is_st`` 统一写 FALSE，不伪造历史；需要时由后续 ST 快照表补齐。

用法：
    python scripts/build_tradable_flags.py --start 2015-01-01 --end 2026-11-05
    python scripts/build_tradable_flags.py --start 2015-01-01 --end 2026-11-05 --apply
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Final

import duckdb
from quant_schema.constants import (
    DIM_STOCK_BASIC,
    FACT_DAILY,
    FACT_STK_LIMIT,
    FACT_TRADABLE_FLAG,
)

from data_pipeline.config import DUCKDB_PATH, LOG_LEVEL, market_db_path
from data_pipeline.db import DEFAULT_MEMORY_LIMIT, DEFAULT_THREADS, database

LOG = logging.getLogger("build_tradable_flags")

_FLAG_SQL: Final[str] = f"""
WITH base AS (
    SELECT
        d.ts_code,
        d.trade_date,
        (d.vol IS NULL OR d.vol = 0) AS is_suspended,
        (
            l.up_limit IS NOT NULL
            AND d.close >= l.up_limit - 1e-9
            AND (s.list_date IS NULL OR d.trade_date > s.list_date)
        ) AS is_limit_up,
        (
            l.down_limit IS NOT NULL
            AND d.close <= l.down_limit + 1e-9
            AND (s.list_date IS NULL OR d.trade_date > s.list_date)
        ) AS is_limit_down,
        CASE
            WHEN s.ts_code IS NULL THEN TRUE
            ELSE (s.list_date IS NULL OR d.trade_date >= s.list_date)
             AND (s.delist_date IS NULL OR d.trade_date < s.delist_date)
        END AS in_universe
    FROM "{FACT_DAILY}" d
    LEFT JOIN "{FACT_STK_LIMIT}" l
      ON l.ts_code = d.ts_code AND l.trade_date = d.trade_date
    LEFT JOIN "{DIM_STOCK_BASIC}" s
      ON s.ts_code = d.ts_code
    WHERE d.trade_date BETWEEN ? AND ?
)
SELECT
    ts_code,
    trade_date,
    is_suspended,
    FALSE AS is_st,
    is_limit_up,
    is_limit_down,
    (NOT is_suspended AND NOT is_limit_up AND in_universe) AS is_buyable,
    (NOT is_suspended AND NOT is_limit_down AND in_universe) AS is_sellable,
    in_universe
FROM base
"""

_UPSERT_SQL: Final[str] = f"""
INSERT INTO "{FACT_TRADABLE_FLAG}" (
    ts_code, trade_date, is_suspended, is_st, is_limit_up, is_limit_down,
    is_buyable, is_sellable, in_universe
)
{_FLAG_SQL}
ON CONFLICT (ts_code, trade_date) DO UPDATE SET
    is_suspended = excluded.is_suspended,
    is_st = excluded.is_st,
    is_limit_up = excluded.is_limit_up,
    is_limit_down = excluded.is_limit_down,
    is_buyable = excluded.is_buyable,
    is_sellable = excluded.is_sellable,
    in_universe = excluded.in_universe
"""


def _count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return int(con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])


def _count_range(
    con: duckdb.DuckDBPyConnection, table: str, start: date, end: date
) -> tuple[int, int]:
    row = con.execute(
        f'SELECT count(*), count(DISTINCT ts_code) FROM "{table}" '
        "WHERE trade_date BETWEEN ? AND ?",
        [start, end],
    ).fetchone()
    return (0, 0) if row is None else (int(row[0]), int(row[1]))


def build_flags(
    con: duckdb.DuckDBPyConnection,
    start: date,
    end: date,
    *,
    apply: bool = False,
) -> dict[str, int | bool]:
    """计算并可选写入 ``fact_tradable_flag``；返回统计信息。"""
    if end < start:
        raise ValueError(f"end={end} 早于 start={start}")

    required = (FACT_DAILY, FACT_STK_LIMIT, DIM_STOCK_BASIC, FACT_TRADABLE_FLAG)
    existing = {
        str(row[0])
        for row in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main'"
        ).fetchall()
    }
    missing = [name for name in required if name not in existing]
    if missing:
        raise ValueError(f"缺表 {missing}；请先执行 init_market_db.py init")

    if _count(con, FACT_DAILY) == 0:
        raise ValueError(f"{FACT_DAILY} 为空，无法派生可交易标记")
    if _count(con, FACT_STK_LIMIT) == 0:
        LOG.warning("%s 为空：is_limit_up/down 将全部为 FALSE", FACT_STK_LIMIT)
    if _count(con, DIM_STOCK_BASIC) == 0:
        LOG.warning(
            "%s 为空：in_universe 退化为 True（fact_daily 出现即视为在池）",
            DIM_STOCK_BASIC,
        )

    rows, codes = _count_range(con, FACT_DAILY, start, end)
    stats: dict[str, int | bool] = {
        "rows": rows,
        "codes": codes,
        "applied": apply,
    }
    if rows == 0:
        LOG.warning("%s 在 %s..%s 没有数据", FACT_DAILY, start, end)
        return stats

    LOG.info("待派生 %d 行 / %d 只股票（%s..%s）", rows, codes, start, end)
    if not apply:
        LOG.info("dry-run：未写入；确认后加 --apply")
        return stats

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(_UPSERT_SQL, [start, end])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    written = _count_range(con, FACT_TRADABLE_FLAG, start, end)[0]
    stats["written"] = written
    LOG.info("写入 %s：%d 行", FACT_TRADABLE_FLAG, written)
    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build_tradable_flags.py")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--start", default="2015-01-01", help="YYYY-MM-DD")
    parser.add_argument(
        "--end", default=None, help="YYYY-MM-DD；默认 fact_daily 最大日期"
    )
    parser.add_argument("--apply", action="store_true", help="真正写入；默认 dry-run")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument(
        "--memory-limit", dest="memory_limit", default=DEFAULT_MEMORY_LIMIT
    )
    parser.add_argument(
        "--log-level", default=LOG_LEVEL, choices=("DEBUG", "INFO", "WARNING", "ERROR")
    )
    return parser


def _setup_logging(level: str) -> None:
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s | %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.log_level)
    db_path = args.db or Path(
        market_db_path("prod") or DUCKDB_PATH or "data/market.duckdb"
    )
    start = date.fromisoformat(args.start)
    try:
        with database(
            db_path, threads=args.threads, memory_limit=args.memory_limit
        ) as con:
            if args.end:
                end = date.fromisoformat(args.end)
            else:
                row = con.execute(
                    f'SELECT max(trade_date) FROM "{FACT_DAILY}"'
                ).fetchone()
                if row is None or row[0] is None:
                    raise ValueError(f"{FACT_DAILY} 为空")
                end = row[0]
            stats = build_flags(con, start, end, apply=args.apply)
            LOG.info("完成：%s", stats)
    except Exception as exc:  # noqa: BLE001 - CLI 顶层
        LOG.error("失败：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
