"""data_pipeline.db — 统一的 DuckDB 连接器。

被 ``data_pipeline`` 自己的脚本、``quant-baseline``、``quant-backtest-engine`` 复用，
避免每个项目各写一套 threads / memory_limit / temp_dir / 权限逻辑。

约定：

* 调用方负责 ``close()``，或使用 ``database()`` 上下文管理器；
* ``read_only=True`` 时不做 chmod、不创建文件；
* 只设置会话级 PRAGMA，不建表、不写业务数据。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

import duckdb

LOG = logging.getLogger("data_pipeline.db")

DEFAULT_THREADS: Final[int] = 6
DEFAULT_MEMORY_LIMIT: Final[str] = "6GB"
_MEMORY_LIMIT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\d+(?:\.\d+)?(?:MB|GB|TB)$", re.IGNORECASE
)


class ConfigError(ValueError):
    """连接参数非法。"""


def quote_literal(value: str) -> str:
    return value.replace("'", "''")


def validate_threads(threads: int) -> int:
    if not isinstance(threads, int) or isinstance(threads, bool):
        raise ConfigError(f"threads 必须是 int，收到 {type(threads).__name__}")
    if not 1 <= threads <= 128:
        raise ConfigError(f"threads 必须在 [1, 128]，收到 {threads}")
    return threads


def validate_memory_limit(memory_limit: str) -> str:
    if not isinstance(memory_limit, str) or not _MEMORY_LIMIT_RE.match(
        memory_limit.strip()
    ):
        raise ConfigError(f"memory_limit 非法：{memory_limit!r}，示例 '4GB'")
    return memory_limit.strip()


def _chmod_quiet(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError as exc:  # pragma: no cover - Windows 常见
        LOG.debug("chmod %s 失败：%s", path, exc)


def connect(
    db_path: str | Path,
    *,
    threads: int = DEFAULT_THREADS,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_dir: str | Path | None = None,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """打开（并按需创建）DuckDB 连接；调用方负责 close()。"""
    validate_threads(threads)
    validate_memory_limit(memory_limit)

    is_memory = str(db_path) == ":memory:"
    target = str(db_path)
    if not is_memory:
        path = Path(db_path)
        if not read_only:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)  # SECURITY
        target = str(path)

    con = duckdb.connect(target, read_only=read_only)
    try:
        con.execute(f"SET threads = {validate_threads(threads)}")
        con.execute(f"SET memory_limit = '{validate_memory_limit(memory_limit)}'")
        con.execute("SET preserve_insertion_order = false")
        con.execute("SET enable_progress_bar = false")
        if temp_dir is not None:
            tmp = Path(temp_dir)
            if not read_only:
                tmp.mkdir(parents=True, exist_ok=True, mode=0o700)
            con.execute(f"SET temp_directory = '{quote_literal(str(tmp.resolve()))}'")
    except Exception:
        con.close()
        raise

    if not is_memory and not read_only:
        _chmod_quiet(Path(db_path), 0o600)
    return con


@contextmanager
def database(
    db_path: str | Path,
    *,
    threads: int = DEFAULT_THREADS,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    temp_dir: str | Path | None = None,
    read_only: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """with 版本连接，退出即关闭。"""
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
        except Exception as exc:  # noqa: BLE001
            LOG.warning("关闭连接异常：%s", exc)


__all__ = [
    "DEFAULT_MEMORY_LIMIT",
    "DEFAULT_THREADS",
    "ConfigError",
    "connect",
    "database",
    "quote_literal",
    "validate_memory_limit",
    "validate_threads",
]
