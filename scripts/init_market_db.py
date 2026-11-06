#!/usr/bin/env python3
"""
init_market_db.py — DuckDB 量化库结构初始化（warehouse 组件）

Rules:
    只建表、建视图、校验结构；表结构定义来自 quant_schema.market_ddl。
Constraints:
    import 本模块 -> connect()/database() 拿连接 -> init_schema(con) 一次

用法：
    python init_market_db.py init  --db "$DUCKDB_PATH"
    python init_market_db.py check --db "$DUCKDB_PATH"

与 factor 组件的关系：
    meta_schema_version 是组件无关的共享表，warehouse 与 factor 各占一行。
    installed_version(con, component) 默认查 'warehouse'，向后兼容。
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import duckdb
from quant_schema._ddl import Table, normalise_type
from quant_schema.constants import WAREHOUSE_COMPONENT, WAREHOUSE_SCHEMA_VERSION
from quant_schema.market_ddl import WAREHOUSE_TABLES, WAREHOUSE_VIEWS

from data_pipeline.config import DUCKDB_PATH, LOG_LEVEL, market_db_path
from data_pipeline.db import (
    DEFAULT_MEMORY_LIMIT,
    DEFAULT_THREADS,
    ConfigError,
    connect,
    database,
)

__all__ = [
    "TABLES",
    "VIEWS",
    "ConfigError",
    "SchemaError",
    "connect",
    "database",
    "init_schema",
    "installed_version",
    "table_row_counts",
    "verify_schema",
]

LOG = logging.getLogger("init_market_db")
SCHEMA_VERSION: Final[str] = WAREHOUSE_SCHEMA_VERSION
COMPONENT: Final[str] = WAREHOUSE_COMPONENT

# 兼容既有调用方 / 测试：表与视图定义以 quant_schema 为准。
TABLES: Final[tuple[Table, ...]] = WAREHOUSE_TABLES
VIEWS: Final[dict[str, str]] = WAREHOUSE_VIEWS


def _load_config_defaults() -> tuple[Path, str]:
    db_path = Path(DUCKDB_PATH) if DUCKDB_PATH else Path("data/market.duckdb")
    return db_path, LOG_LEVEL


DEFAULT_DB_PATH, DEFAULT_LOG_LEVEL = _load_config_defaults()

_COMPONENT_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_TYPE_ALIASES: Final[dict[str, str]] = {"TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE"}
# 兼容旧代码引用
_normalise_type = normalise_type


class SchemaError(RuntimeError):
    """库结构与代码期望不一致"""


# ---------------------------------------------------------------------------
# 组件校验（连接器复用 data_pipeline.db）
# ---------------------------------------------------------------------------
def _validate_component(component: str) -> str:
    if not isinstance(component, str) or not _COMPONENT_RE.fullmatch(component):
        raise ConfigError(f"component 非法：{component!r}，示例 'warehouse'")
    return component


# ---------------------------------------------------------------------------
# 建表 / 校验
# ---------------------------------------------------------------------------
def _scalar(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: Sequence[object] = (),
) -> Any:
    """取单行单列；无结果行说明库结构异常，抛 SchemaError 而非静默返回 None。"""
    cursor = con.execute(sql, list(params)) if params else con.execute(sql)
    rows = cursor.fetchall()
    if not rows:
        raise SchemaError(f"查询未返回任何行：{sql}")
    return rows[0][0]


def verify_schema(con: duckdb.DuckDBPyConnection) -> None:
    """比对实际表结构与 quant_schema.market_ddl.WAREHOUSE_TABLES，不一致抛错。"""
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
            "schema 校验失败（请勿直接修改建表语句，需走迁移）：" + "; ".join(problems)
        )


def init_schema(con: duckdb.DuckDBPyConnection, *, verify: bool = True) -> None:
    """幂等建表 + 建视图 + 记录版本号；DDL 与校验同事务，失败整体回滚。"""
    con.execute("BEGIN TRANSACTION")
    try:
        for table in TABLES:
            con.execute(table.ddl())

        if verify:
            verify_schema(con)  # 提前校验，残缺表在这里抛 SchemaError

        for name, sql in VIEWS.items():
            con.execute(f'CREATE OR REPLACE VIEW "{name}" AS {sql}')

        con.execute(
            "INSERT INTO meta_schema_version (component, version) VALUES (?, ?) "
            "ON CONFLICT (component) DO UPDATE SET "
            "version = excluded.version, applied_at = now()",
            [COMPONENT, SCHEMA_VERSION],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def installed_version(
    con: duckdb.DuckDBPyConnection,
    component: str = COMPONENT,
) -> str | None:
    """返回指定组件版本；默认 'warehouse'。行不存在返回 None。"""
    component = _validate_component(component)
    rows = con.execute(
        "SELECT version FROM meta_schema_version WHERE component = ?",
        [component],
    ).fetchall()
    return None if not rows else str(rows[0][0])


def table_row_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """各表当前行数；表不存在记 -1，供调用方打印状态用。"""
    existing: set[str] = {
        str(row[0])
        for row in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main'"
        ).fetchall()
    }
    out: dict[str, int] = {}
    for table in TABLES:
        if table.name not in existing:
            out[table.name] = -1
            continue
        # SECURITY: table.name 来自模块常量，无外部输入
        out[table.name] = int(_scalar(con, f'SELECT count(*) FROM "{table.name}"'))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="init_market_db.py", description="DuckDB 量化库结构初始化（warehouse）"
    )
    parser.add_argument("command", nargs="?", default="init", choices=("init", "check"))
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--env", choices=("prod", "test"), default="prod")
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.log_level)
    db_path = args.db or Path(market_db_path(args.env) or DEFAULT_DB_PATH)
    try:
        with database(
            db_path,
            threads=args.threads,
            memory_limit=args.memory_limit,
            temp_dir=args.temp_dir,
        ) as con:
            if args.command == "check":
                verify_schema(con)
            else:
                init_schema(con)
            counts = table_row_counts(con)
            LOG.info(
                "%s 完成  db=%s  component=%s  version=%s",
                "校验" if args.command == "check" else "初始化",
                db_path,
                COMPONENT,
                installed_version(con) or "-",
            )
            for name, rows in counts.items():
                LOG.info("  %-20s %10d", name, rows)
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
