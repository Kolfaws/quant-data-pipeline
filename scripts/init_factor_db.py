#!/usr/bin/env python3
"""
init_factor_db.py — factor DuckDB 组件结构初始化（market.duckdb）

Rules:
    只追加 factor 组件结构，不重建 warehouse 行情表，不写入业务数据。
    表结构定义来自 quant_schema.market_ddl，本脚本只负责事务、校验与版本。
Constraints:
    先执行 init_market_db.init，再执行 init_factor_db.init；
    同一 DuckDB 文件跨进程只允许一个 RW 连接，初始化与批次写入均需串行。

用法：
    python init_factor_db.py init    --db "$DUCKDB_PATH"
    python init_factor_db.py check   --db "$DUCKDB_PATH"
    python init_factor_db.py refresh --db "$DUCKDB_PATH"   # 因子目录变更后重建宽表视图

复杂度：
    init_schema   O(T + F + C)
    verify_schema O(C + F)
    refresh_views O(F)
    T = 表数（4），F = 活跃因子数，C = 列数
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import duckdb
import init_market_db as _market
from quant_schema._ddl import Table, normalise_type
from quant_schema.constants import FACTOR_COMPONENT, FACTOR_SCHEMA_VERSION
from quant_schema.market_ddl import (
    FACTOR_REQUIRED_WAREHOUSE_TABLES,
    FACTOR_STATIC_VIEWS,
    FACTOR_TABLES,
)

LOG = logging.getLogger("init_factor_db")

SCHEMA_VERSION: Final[str] = FACTOR_SCHEMA_VERSION
COMPONENT: Final[str] = FACTOR_COMPONENT
MIN_WAREHOUSE_VERSION: Final[str] = "1.1.0"

# 复用 market 的异常与连接器，保证两个模块的资源策略完全一致。
ConfigError = _market.ConfigError
SchemaError = _market.SchemaError
connect = _market.connect
database = _market.database
_scalar = _market._scalar
_normalise_type = normalise_type

DEFAULT_DB_PATH: Final[Path] = _market.DEFAULT_DB_PATH
DEFAULT_THREADS: Final[int] = _market.DEFAULT_THREADS
DEFAULT_MEMORY_LIMIT: Final[str] = _market.DEFAULT_MEMORY_LIMIT
DEFAULT_LOG_LEVEL: Final[str] = _market.DEFAULT_LOG_LEVEL

_COMPONENT_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_SEMVER_RE: Final[re.Pattern[str]] = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

_SHARED_TABLE_NAMES: Final[tuple[str, ...]] = (
    "meta_schema_version",
    "meta_ingest_log",
)

# DDL 直接复用 market 的 Table 对象，确保共享表“逐字一致”。
SHARED_TABLES: Final[tuple[Table, ...]] = tuple(
    table for table in _market.TABLES if table.name in _SHARED_TABLE_NAMES
)
if {table.name for table in SHARED_TABLES} != set(_SHARED_TABLE_NAMES):
    raise RuntimeError(
        "init_market_db.TABLES 缺少共享基础表，无法保证 factor 组件结构一致"
    )

TABLES: Final[tuple[Table, ...]] = SHARED_TABLES + FACTOR_TABLES

# v_factor_wide 的 SQL 动态生成；None 表示“由 _create_wide_view 负责”。
VIEWS: Final[dict[str, str | None]] = {
    "v_factor_wide": None,
    "v_factor_valid": FACTOR_STATIC_VIEWS["v_factor_valid"],
}
VIEW_NAMES: Final[tuple[str, ...]] = tuple(VIEWS)

REQUIRED_WAREHOUSE_TABLES: Final[tuple[str, ...]] = FACTOR_REQUIRED_WAREHOUSE_TABLES


# ---------------------------------------------------------------------------
# 校验辅助
# ---------------------------------------------------------------------------
def _validate_component(component: str) -> str:
    if not isinstance(component, str) or not _COMPONENT_RE.fullmatch(component):
        raise ConfigError(f"component 非法：{component!r}，示例 'warehouse'")
    return component


def _version_tuple(version: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.fullmatch(version.strip())
    if match is None:
        raise SchemaError(f"非法版本号：{version!r}")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _main_tables(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _main_views(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT view_name FROM duckdb_views() WHERE schema_name = 'main'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _relation_columns(
    con: duckdb.DuckDBPyConnection,
    name: str,
) -> list[tuple[str, str]]:
    if name not in VIEW_NAMES:
        raise ValueError(f"未知视图：{name}")
    rows = con.execute(f'DESCRIBE "{name}"').fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def _require_warehouse(con: duckdb.DuckDBPyConnection) -> None:
    """factor 组件的前置依赖断言：warehouse 已建、版本达标、必需表齐全。"""
    existing = _main_tables(con)
    if "meta_schema_version" not in existing:
        raise SchemaError("未找到 warehouse 组件：请先执行 init_market_db.py init")

    version = installed_version(con, "warehouse")
    if version is None:
        raise SchemaError("warehouse 组件未初始化：请先执行 init_market_db.py init")

    if _version_tuple(version) < _version_tuple(MIN_WAREHOUSE_VERSION):
        raise SchemaError(
            f"warehouse 版本 {version} < 最低要求 {MIN_WAREHOUSE_VERSION}；"
            "请先升级 init_market_db"
        )

    missing = [name for name in REQUIRED_WAREHOUSE_TABLES if name not in existing]
    if missing:
        raise SchemaError(
            f"warehouse 组件缺表 {missing}：请先执行 init_market_db.py init"
        )


def installed_version(
    con: duckdb.DuckDBPyConnection,
    component: str = COMPONENT,
) -> str | None:
    """返回指定组件版本；默认 'factor'，可显式查询 'warehouse'。"""
    component = _validate_component(component)
    rows = con.execute(
        "SELECT version FROM meta_schema_version WHERE component = ?",
        [component],
    ).fetchall()
    return None if not rows else str(rows[0][0])


# ---------------------------------------------------------------------------
# 视图
# ---------------------------------------------------------------------------
def _active_factor_ids(con: duckdb.DuckDBPyConnection) -> list[int]:
    rows = con.execute(
        "SELECT factor_id FROM meta_factor_registry "
        "WHERE is_active = TRUE ORDER BY factor_id"
    ).fetchall()
    return [int(row[0]) for row in rows]


def _pivot_sql(active_ids: Sequence[int]) -> str:
    in_list = ", ".join(str(int(fid)) for fid in active_ids)
    return (
        "PIVOT fact_factor_daily "
        f"ON factor_id IN ({in_list}) "
        "USING FIRST(value) "
        "GROUP BY ts_code, trade_date "
        "ORDER BY ts_code, trade_date"
    )


def _conditional_wide_sql(active_ids: Sequence[int]) -> str:
    """回退路径：条件聚合，保证空表时也能得到固定列数。"""
    projected = ["ts_code", "trade_date"]
    for fid in active_ids:
        projected.append(
            f'FIRST(value) FILTER (WHERE factor_id = {int(fid)}) AS "{int(fid)}"'
        )
    return (
        "SELECT "
        + ", ".join(projected)
        + " FROM fact_factor_daily "
        + "GROUP BY ts_code, trade_date "
        + "ORDER BY ts_code, trade_date"
    )


def _create_wide_view(
    con: duckdb.DuckDBPyConnection,
    active_ids: Sequence[int],
) -> None:
    if not active_ids:
        con.execute(
            'CREATE OR REPLACE VIEW "v_factor_wide" AS '
            "SELECT ts_code, trade_date FROM fact_factor_daily "
            "GROUP BY ts_code, trade_date "
            "ORDER BY ts_code, trade_date"
        )
        return

    expected = 2 + len(active_ids)
    try:
        con.execute(
            f'CREATE OR REPLACE VIEW "v_factor_wide" AS {_pivot_sql(active_ids)}'
        )
        actual = len(_relation_columns(con, "v_factor_wide"))
        if actual != expected:
            raise SchemaError(f"PIVOT 列数 {actual} != {expected}，回退条件聚合")
    except (duckdb.Error, SchemaError) as exc:
        LOG.warning("PIVOT 创建 v_factor_wide 失败，回退条件聚合：%s", exc)
        con.execute(
            f'CREATE OR REPLACE VIEW "v_factor_wide" AS '
            f"{_conditional_wide_sql(active_ids)}"
        )


def _create_views(con: duckdb.DuckDBPyConnection) -> None:
    _create_wide_view(con, _active_factor_ids(con))
    con.execute(
        f'CREATE OR REPLACE VIEW "v_factor_valid" AS '
        f"{FACTOR_STATIC_VIEWS['v_factor_valid']}"
    )


def _verify_views(con: duckdb.DuckDBPyConnection) -> None:
    existing = _main_views(con)
    missing = [name for name in VIEW_NAMES if name not in existing]
    if missing:
        raise SchemaError("缺视图 " + ", ".join(missing))

    valid_cols = [name for name, _ in _relation_columns(con, "v_factor_valid")]
    expected_valid = ["ts_code", "trade_date", "factor_id", "value", "is_stale"]

    wide_cols = [name for name, _ in _relation_columns(con, "v_factor_wide")]
    expected_wide = 2 + len(_active_factor_ids(con))

    problems: list[str] = []
    if valid_cols != expected_valid:
        problems.append(f"v_factor_valid 列 {valid_cols} != {expected_valid}")
    if len(wide_cols) < 2 or wide_cols[0] != "ts_code" or wide_cols[1] != "trade_date":
        problems.append(f"v_factor_wide 前两列非法：{wide_cols[:2]}")
    if len(wide_cols) != expected_wide:
        problems.append(f"v_factor_wide 列数 {len(wide_cols)} != {expected_wide}")

    if problems:
        raise SchemaError("schema 校验失败（factor 视图）：" + "; ".join(problems))


# ---------------------------------------------------------------------------
# 建表 / 校验 / 刷新
# ---------------------------------------------------------------------------
def verify_schema(
    con: duckdb.DuckDBPyConnection,
    *,
    verify_views: bool = True,
) -> None:
    """严格比对共享表 + factor 表；结构漂移抛 SchemaError。"""
    _require_warehouse(con)

    rows = con.execute(
        "SELECT table_name, column_name, data_type "
        "FROM duckdb_columns() WHERE schema_name = 'main'"
    ).fetchall()

    actual: dict[str, dict[str, str]] = {}
    for table_name, column_name, data_type in rows:
        actual.setdefault(str(table_name), {})[str(column_name)] = normalise_type(
            str(data_type)
        )

    problems: list[str] = []
    for table in TABLES:
        found = actual.get(table.name)
        if found is None:
            problems.append(f"缺表 {table.name}")
            continue

        expected = table.expected_types
        for column, want in expected.items():
            got = found.get(column)
            if got is None:
                problems.append(f"{table.name}.{column} 缺失")
            elif got != want:
                problems.append(f"{table.name}.{column} 类型 {got} != {want}")

        extra = sorted(set(found) - set(expected))
        if extra:
            problems.append(f"{table.name} 存在多余列 {extra}")

    if problems:
        raise SchemaError(
            "schema 校验失败（factor，请勿直接修改建表语句，需走迁移）："
            + "; ".join(problems)
        )

    if verify_views:
        _verify_views(con)


def init_schema(
    con: duckdb.DuckDBPyConnection,
    *,
    verify: bool = True,
) -> None:
    """幂等初始化 factor 组件（单事务）。"""
    con.execute("BEGIN TRANSACTION")
    try:
        _require_warehouse(con)

        for table in TABLES:
            con.execute(table.ddl())

        if verify:
            verify_schema(con, verify_views=False)

        _create_views(con)

        if verify:
            _verify_views(con)

        con.execute(
            "INSERT INTO meta_schema_version (component, version) "
            "VALUES (?, ?) "
            "ON CONFLICT (component) DO UPDATE SET "
            "version = excluded.version, applied_at = now()",
            [COMPONENT, SCHEMA_VERSION],
        )

        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def refresh_views(con: duckdb.DuckDBPyConnection) -> None:
    """在因子目录变更后重建 v_factor_wide / v_factor_valid（自带事务）。"""
    con.execute("BEGIN TRANSACTION")
    try:
        verify_schema(con, verify_views=False)
        _create_views(con)
        _verify_views(con)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def table_row_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """仅统计 factor 模块 TABLES（含共享基础表）；表不存在记 -1。"""
    existing = _main_tables(con)
    out: dict[str, int] = {}
    for table in TABLES:
        if table.name not in existing:
            out[table.name] = -1
            continue
        out[table.name] = int(_scalar(con, f'SELECT count(*) FROM "{table.name}"'))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="init_factor_db.py",
        description="factor DuckDB 组件结构初始化（market.duckdb）",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="init",
        choices=("init", "check", "refresh"),
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument(
        "--memory-limit", dest="memory_limit", default=DEFAULT_MEMORY_LIMIT
    )
    parser.add_argument("--temp-dir", dest="temp_dir", type=Path, default=None)
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser


def _setup_logging(level: str) -> None:
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s | %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


_ACTION_LABEL: Final[dict[str, str]] = {
    "init": "初始化",
    "check": "校验",
    "refresh": "刷新视图",
}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.log_level)

    try:
        with database(
            args.db,
            threads=args.threads,
            memory_limit=args.memory_limit,
            temp_dir=args.temp_dir,
        ) as con:
            if args.command == "check":
                verify_schema(con)
            elif args.command == "refresh":
                refresh_views(con)
            else:
                init_schema(con)

            counts = table_row_counts(con)
            LOG.info(
                "%s 完成  db=%s  component=%s  version=%s",
                _ACTION_LABEL[args.command],
                args.db,
                COMPONENT,
                installed_version(con) or "-",
            )
            for name, rows in counts.items():
                LOG.info("  %-24s %10d", name, rows)

    except ConfigError as exc:
        LOG.error("配置错误：%s", exc)
        return 2
    except duckdb.Error as exc:
        LOG.error("DuckDB 错误：%s", exc)
        return 1
    except SchemaError as exc:
        LOG.error("%s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
