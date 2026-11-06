#!/usr/bin/env python3
"""sync_test_market.py — 把正式行情复制到测试库，用于因子/基准实验。

测试库的因子层保持独立；默认 dry-run，``--apply`` 才覆盖测试库的 warehouse 表。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
from quant_schema.constants import (
    MARKET_WAREHOUSE_TABLES,
    META_INGEST_LOG,
    META_SCHEMA_VERSION,
)

from data_pipeline.config import market_db_path


def _quote(value: str) -> str:
    return value.replace("'", "''")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="正式行情 -> 测试库")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    prod_path = market_db_path("prod")
    test_path = market_db_path("test")
    if not prod_path or not test_path:
        print("缺少 MARKET_DB_PATH 或 MARKET_TEST_DB_PATH", file=sys.stderr)
        return 2
    if Path(prod_path).resolve() == Path(test_path).resolve():
        print("正式库与测试库路径相同，拒绝执行", file=sys.stderr)
        return 2
    if not Path(prod_path).is_file() or not Path(test_path).is_file():
        print("正式库或测试库不存在", file=sys.stderr)
        return 2

    tables = [
        name
        for name in MARKET_WAREHOUSE_TABLES
        if name not in {META_SCHEMA_VERSION, META_INGEST_LOG}
    ]
    test = duckdb.connect(str(test_path))
    try:
        test.execute(f"ATTACH '{_quote(str(prod_path))}' AS prod_src (READ_ONLY)")
        try:
            counts = {
                name: int(
                    test.execute(f'SELECT count(*) FROM prod_src."{name}"').fetchall()[
                        0
                    ][0]
                )
                for name in tables
            }
            for name, count in counts.items():
                print(f"{name}: {count}")
            if not args.apply:
                print("dry-run：未写入。确认后加 --apply")
                return 0

            test.execute("BEGIN TRANSACTION")
            try:
                for name in tables:
                    test.execute(f'DELETE FROM "{name}"')
                    test.execute(
                        f'INSERT INTO "{name}" SELECT * FROM prod_src."{name}"'
                    )
                test.execute("COMMIT")
            except Exception:
                test.execute("ROLLBACK")
                raise
            print(f"已同步 {len(tables)} 张 warehouse 表到测试库")
        finally:
            test.execute("DETACH prod_src")
    finally:
        test.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
