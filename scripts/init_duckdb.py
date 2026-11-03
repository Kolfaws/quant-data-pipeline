#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
init_duckdb.py — DuckDB 量化库结构初始化

Rules: 只建表、建视图、校验结构
Constraints: import 本模块 -> connect()/database() 拿连接 -> init_schema(con) 一次

用法：
    python init_duckdb.py init  --db data/market.duckdb
    python init_duckdb.py check --db data/market.duckdb
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final, Any

import duckdb

LOG = logging.getLogger("init_duckdb")
SCHEMA_VERSION: Final[str] = "1.1.0"


def _load_config_defaults() -> tuple[Path, str]:
    """在函数内部处理路径和导入"""
    try:
        # 将项目根目录加入 sys.path (只在运行函数时生效)
        root_dir = Path(__file__).resolve().parent.parent
        if str(root_dir) not in sys.path:
            sys.path.insert(0, str(root_dir))

        # 在函数内导入
        from src.data_pipeline.config import DUCKDB_PATH, LOG_LEVEL

        db_path = Path(DUCKDB_PATH) if DUCKDB_PATH else Path("data/market.duckdb")
        return db_path, LOG_LEVEL
    except (ImportError, ModuleNotFoundError):
        # 如果包没装好或者找不到，安全回退到默认值
        return Path("data/market.duckdb"), "INFO"


DEFAULT_DB_PATH, DEFAULT_LOG_LEVEL = _load_config_defaults()
DEFAULT_THREADS: Final[int] = 6
DEFAULT_MEMORY_LIMIT: Final[str] = "6GB"

_MEMORY_LIMIT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\d+(?:\.\d+)?(?:MB|GB|TB)$", re.I
)
_TYPE_ALIASES: Final[dict[str, str]] = {"TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE"}


class ConfigError(ValueError):
    """参数非法"""


class SchemaError(RuntimeError):
    """库结构与代码期望不一致"""


# ---------------------------------------------------------------------------
# 表定义
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Table:
    name: str
    columns: tuple[tuple[str, str], ...]
    constraints: tuple[str, ...] = ()

    def ddl(self) -> str:
        body = ",\n        ".join(f'"{c}" {t}' for c, t in self.columns)
        tail = "".join(f",\n        {c}" for c in self.constraints)
        return (
            f'CREATE TABLE IF NOT EXISTS "{self.name}" (\n        {body}{tail}\n    )'
        )

    @property
    def expected_types(self) -> dict[str, str]:
        return {
            col: _normalise_type(decl.split(" ", 1)[0]) for col, decl in self.columns
        }


def _normalise_type(raw: str) -> str:
    upper = raw.strip().upper()
    return _TYPE_ALIASES.get(upper, upper)


TABLES: Final[tuple[Table, ...]] = (
    Table(
        name="meta_schema_version",
        columns=(
            ("component", "VARCHAR NOT NULL"),
            ("version", "VARCHAR NOT NULL"),
            ("applied_at", "TIMESTAMPTZ NOT NULL DEFAULT current_timestamp"),
        ),
        constraints=("PRIMARY KEY (component)",),
    ),
    Table(
        name="meta_ingest_log",
        columns=(
            ("table_name", "VARCHAR NOT NULL"),
            ("scope_key", "VARCHAR NOT NULL"),
            ("row_count", "BIGINT NOT NULL DEFAULT 0"),
            ("status", "VARCHAR NOT NULL"),
            ("detail", "VARCHAR"),
            ("started_at", "TIMESTAMPTZ NOT NULL"),
            ("finished_at", "TIMESTAMPTZ"),
        ),
        constraints=("PRIMARY KEY (table_name, scope_key)",),
    ),
    Table(
        name="dim_stock_basic",
        columns=(
            ("ts_code", "VARCHAR NOT NULL"),
            ("symbol", "VARCHAR"),
            ("name", "VARCHAR"),
            ("area", "VARCHAR"),
            ("industry", "VARCHAR"),
            ("market", "VARCHAR"),
            ("exchange", "VARCHAR"),
            ("list_status", "VARCHAR NOT NULL"),
            ("list_date", "DATE"),
            ("delist_date", "DATE"),
            ("is_hs", "VARCHAR"),
        ),
    ),
    Table(
        name="dim_trade_cal",
        columns=(
            ("exchange", "VARCHAR NOT NULL"),
            ("cal_date", "DATE NOT NULL"),
            ("is_open", "BOOLEAN NOT NULL"),
            ("pretrade_date", "DATE"),
        ),
    ),
    Table(
        name="fact_daily",
        columns=(
            ("ts_code", "VARCHAR NOT NULL"),
            ("trade_date", "DATE NOT NULL"),
            ("open", "DOUBLE"),
            ("high", "DOUBLE"),
            ("low", "DOUBLE"),
            ("close", "DOUBLE"),
            ("pre_close", "DOUBLE"),
            ("chg", "DOUBLE"),
            ("pct_chg", "DOUBLE"),
            ("vol", "DOUBLE"),
            ("amount", "DECIMAL(20,4)"),
        ),
    ),
    Table(
        name="fact_adj_factor",
        columns=(
            ("ts_code", "VARCHAR NOT NULL"),
            ("trade_date", "DATE NOT NULL"),
            ("adj_factor", "DOUBLE"),
        ),
    ),
    Table(
        name="fact_daily_basic",
        columns=(
            ("ts_code", "VARCHAR NOT NULL"),
            ("trade_date", "DATE NOT NULL"),
            ("turnover_rate", "DOUBLE"),
            ("turnover_rate_f", "DOUBLE"),
            ("volume_ratio", "DOUBLE"),
            ("pe", "DOUBLE"),
            ("pe_ttm", "DOUBLE"),
            ("pb", "DOUBLE"),
            ("ps", "DOUBLE"),
            ("ps_ttm", "DOUBLE"),
            ("dv_ratio", "DOUBLE"),
            ("dv_ttm", "DOUBLE"),
            ("total_share", "DOUBLE"),
            ("float_share", "DOUBLE"),
            ("free_share", "DOUBLE"),
            ("total_mv", "DECIMAL(20,4)"),
            ("circ_mv", "DECIMAL(20,4)"),
        ),
    ),
    Table(
        name="fact_stk_limit",
        columns=(
            ("ts_code", "VARCHAR NOT NULL"),
            ("trade_date", "DATE NOT NULL"),
            ("pre_close", "DOUBLE"),
            ("up_limit", "DOUBLE"),
            ("down_limit", "DOUBLE"),
        ),
    ),
)

_QFQ_SQL: Final[str] = """
WITH base AS (
    SELECT d.ts_code, d.trade_date, d.open, d.high, d.low, d.close, d.pre_close,
           d.chg, d.pct_chg, d.vol, d.amount, f.adj_factor
    FROM fact_daily d
    JOIN fact_adj_factor f
      ON f.ts_code = d.ts_code AND f.trade_date = d.trade_date
),
last_adj AS (
    SELECT ts_code, arg_max(adj_factor, trade_date) AS adj_last
    FROM fact_adj_factor GROUP BY ts_code
)
SELECT b.ts_code, b.trade_date,
       b.open      * b.adj_factor / l.adj_last AS open,
       b.high      * b.adj_factor / l.adj_last AS high,
       b.low       * b.adj_factor / l.adj_last AS low,
       b.close     * b.adj_factor / l.adj_last AS close,
       b.pre_close * b.adj_factor / l.adj_last AS pre_close,
       b.chg       * b.adj_factor / l.adj_last AS chg,
       b.pct_chg, b.vol,
       CAST(b.amount * b.adj_factor / l.adj_last AS DECIMAL(20,4)) AS amount,
       b.adj_factor
FROM base b JOIN last_adj l ON l.ts_code = b.ts_code
"""

_HFQ_SQL: Final[str] = """
SELECT d.ts_code, d.trade_date,
       d.open      * f.adj_factor AS open,
       d.high      * f.adj_factor AS high,
       d.low       * f.adj_factor AS low,
       d.close     * f.adj_factor AS close,
       d.pre_close * f.adj_factor AS pre_close,
       d.vol,
       CAST(d.amount * f.adj_factor AS DECIMAL(20,4)) AS amount,
       f.adj_factor
FROM fact_daily d
JOIN fact_adj_factor f ON f.ts_code = d.ts_code AND f.trade_date = d.trade_date
"""

VIEWS: Final[dict[str, str]] = {
    "v_daily_qfq": _QFQ_SQL,
    "v_daily_hfq": _HFQ_SQL,
}


# ---------------------------------------------------------------------------
# 连接
# ---------------------------------------------------------------------------
def _quote_literal(value: str) -> str:
    return value.replace("'", "''")


def _validate_threads(threads: int) -> int:
    if not isinstance(threads, int) or isinstance(threads, bool):
        raise ConfigError(f"threads 必须是 int，收到 {type(threads).__name__}")
    if not 1 <= threads <= 128:
        raise ConfigError(f"threads 必须在 [1, 128]，收到 {threads}")
    return threads


def _validate_memory_limit(memory_limit: str) -> str:
    if not isinstance(memory_limit, str) or not _MEMORY_LIMIT_RE.match(
        memory_limit.strip()
    ):
        raise ConfigError(f"memory_limit 非法：{memory_limit!r}，示例 '4GB'")
    return memory_limit.strip()


def _chmod_quiet(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError as exc:
        LOG.debug("chmod %s 失败：%s", path, exc)


def connect(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    threads: int = DEFAULT_THREADS,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_dir: str | Path | None = None,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """打开（并按需创建）DuckDB 连接调用方负责 close()"""
    _validate_threads(threads)
    _validate_memory_limit(memory_limit)

    is_memory = str(db_path) == ":memory:"
    target = str(db_path)
    if not is_memory:
        path = Path(db_path)
        path.parent.mkdir(
            parents=True, exist_ok=True, mode=0o700
        )  # SECURITY: 目录 0700
        target = str(path)

    con = duckdb.connect(target, read_only=read_only)
    try:
        # SECURITY: 两个值均已强校验（int / 正则），不存在注入口
        con.execute(f"SET threads = {_validate_threads(threads)}")
        con.execute(f"SET memory_limit = '{_validate_memory_limit(memory_limit)}'")
        con.execute("SET preserve_insertion_order = false")  # PERF: 降大写入内存峰值
        con.execute("SET enable_progress_bar = false")
        if temp_dir is not None:
            tmp = Path(temp_dir)
            tmp.mkdir(
                parents=True, exist_ok=True, mode=0o700
            )  # SECURITY: 临时目录 0700
            con.execute(f"SET temp_directory = '{_quote_literal(str(tmp.resolve()))}'")
    except Exception:
        con.close()
        raise

    if not is_memory and not read_only:
        _chmod_quiet(Path(db_path), 0o600)  # SECURITY: 库文件仅属主可读写
    return con


@contextmanager
def database(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    threads: int = DEFAULT_THREADS,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_dir: str | Path | None = None,
    read_only: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """with 版本连接，退出即关闭"""
    con = connect(
        db_path,
        threads=threads,
        memory_limit=memory_limit,
        temp_dir=temp_dir,
        read_only=read_only,
    )
    try:
        yield con
    finally:
        try:
            con.close()
        except Exception as exc:  # noqa: BLE001 - 关闭异常不得掩盖业务异常
            LOG.warning("关闭连接异常：%s", exc)


# ---------------------------------------------------------------------------
# 建表 / 校验
# ---------------------------------------------------------------------------
def _scalar(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: Sequence[object] = (),
) -> Any:
    """取单行单列 无结果行说明库结构异常，抛 SchemaError 而非静默返回 None"""
    cursor = con.execute(sql, list(params)) if params else con.execute(sql)
    row = cursor.fetchone()
    if row is None:
        raise SchemaError(f"查询未返回任何行：{sql}")
    return row[0]


def verify_schema(con: duckdb.DuckDBPyConnection) -> None:
    """比对实际表结构与 TABLES 定义，不一致抛 SchemaError"""
    rows = con.execute(
        "SELECT table_name, column_name, data_type "
        "FROM duckdb_columns() WHERE schema_name = 'main'"
    ).fetchall()
    actual: dict[str, dict[str, str]] = {}
    for table_name, column_name, data_type in rows:
        actual.setdefault(str(table_name), {})[str(column_name)] = _normalise_type(
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
            "INSERT INTO meta_schema_version (component, version) VALUES ('warehouse', ?) "
            "ON CONFLICT (component) DO UPDATE SET "
            "version = excluded.version, applied_at = now()",
            [SCHEMA_VERSION],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def installed_version(con: duckdb.DuckDBPyConnection) -> str | None:
    row = con.execute(
        "SELECT version FROM meta_schema_version WHERE component = 'warehouse'"
    ).fetchone()
    return None if row is None else str(row[0])


def table_row_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """各表当前行数；表不存在记 -1，供调用方打印状态用"""
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
        out[table.name] = int(_scalar(con, f'SELECT count(*) FROM "{table.name}"'))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="init_duckdb.py", description="DuckDB 量化库结构初始化"
    )
    parser.add_argument("command", nargs="?", default="init", choices=("init", "check"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument(
        "--memory-limit", dest="memory_limit", default=DEFAULT_MEMORY_LIMIT
    )
    parser.add_argument("--temp-dir", dest="temp_dir", type=Path, default=None)
    parser.add_argument(
        "--log-level",
        default=DEFAULT_LOG_LEVEL,  # <--- 使用从 config 读取的默认值
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
    try:
        with database(
            args.db,
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
                "%s 完成  db=%s  version=%s",
                "校验" if args.command == "check" else "初始化",
                args.db,
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
