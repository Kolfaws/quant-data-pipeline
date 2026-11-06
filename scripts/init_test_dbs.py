#!/usr/bin/env python3
"""init_test_dbs.py — 初始化 market_test.duckdb 的 warehouse + factor 结构。

测试库与正式库使用同一套 DDL；路径来自 ``MARKET_TEST_DB_PATH``。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import init_factor_db as factor
import init_market_db as market

from data_pipeline.config import market_db_path

LOG = logging.getLogger("init_test_dbs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化测试 market 库")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(message)s")

    raw = args.db or market_db_path("test")
    if not raw:
        LOG.error("未配置 MARKET_TEST_DB_PATH（或 DUCKDB_TEST_PATH）")
        return 2
    db_path = Path(raw)
    prod = market_db_path("prod")
    if prod and Path(prod).resolve() == db_path.resolve():
        LOG.error("测试库路径不能与正式库相同：%s", db_path)
        return 2

    with market.database(db_path) as con:
        market.init_schema(con)
        factor.init_schema(con)
        LOG.info("测试库初始化完成 db=%s", db_path)
        LOG.info(
            "warehouse=%s factor=%s",
            market.installed_version(con, "warehouse") or "-",
            factor.installed_version(con, "factor") or "-",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
