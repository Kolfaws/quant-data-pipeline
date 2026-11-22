"""data_pipeline.guards — 显式库路径解析与 2010 写入闸门。

本模块统一两条写入安全规则，供 ``scripts/`` 下的写库脚本复用：

1. **路径必须显式**：``--db`` 优先；否则读环境变量。
   ``--env test`` 缺 ``MARKET_TEST_DB_PATH`` 时立即失败，绝不回退正式库；
   非 test 环境缺 ``MARKET_DB_PATH`` 时同样失败，不再回退相对路径默认值。
2. **当前研究库只保留 2010**：目标为 ``MARKET_DB_PATH`` 时，``end`` 晚于
   ``2010-12-31`` 一律 fail-fast；``--allow-post-2010`` 只用于新库/新版本，
   不能解锁当前研究库。

路径在**调用时**读环境变量（而非模块导入时快照），这样 CLI 与进程内测试
都能拿到当前环境。错误统一抛 :class:`data_pipeline.db.ConfigError`
（CLI 退出码 2）。
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import data_pipeline.config  # noqa: F401  # 导入即加载 .env（真实环境变量优先）
from data_pipeline.db import ConfigError

#: 当前 2010 研究库允许写入的最后日期（含）。
RESEARCH_LAST_DATE: date = date(2010, 12, 31)

#: 正式库/测试库路径环境变量及其兼容旧名。
_PROD_DB_ENV: tuple[str, ...] = ("MARKET_DB_PATH", "DUCKDB_PATH")
_TEST_DB_ENV: tuple[str, ...] = ("MARKET_TEST_DB_PATH", "DUCKDB_TEST_PATH")

__all__ = [
    "RESEARCH_LAST_DATE",
    "enforce_research_2010_gate",
    "require_market_db_path",
]


def _env_value(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def _same_path(left: str | Path, right: str | Path) -> bool:
    """比较两个库路径是否指向同一文件；不要求文件已存在。"""
    left_path = Path(str(left))
    right_path = Path(str(right))
    try:
        left_resolved = left_path.resolve()
        right_resolved = right_path.resolve()
    except OSError:  # pragma: no cover - 极端路径/权限问题
        return os.path.normcase(str(left_path)) == os.path.normcase(str(right_path))
    return os.path.normcase(str(left_resolved)) == os.path.normcase(str(right_resolved))


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ConfigError(f"非法日期：{value!r}；要求 YYYY-MM-DD") from exc
    raise ConfigError(f"非法日期类型：{type(value).__name__}")


def require_market_db_path(
    db: str | Path | None = None,
    *,
    env: str = "prod",
) -> Path:
    """解析写库目标路径：``--db`` 优先，否则按环境读变量，禁止默认回退。

    Raises:
        ConfigError: ``--env test`` 缺 ``MARKET_TEST_DB_PATH``、prod 缺
            ``MARKET_DB_PATH``、环境名非法，或 test 路径与正式库相同。
    """
    if db is not None and str(db).strip():
        return Path(str(db))

    if env == "test":
        raw = _env_value(_TEST_DB_ENV)
        if not raw:
            raise ConfigError(
                "--env test 需要显式配置 MARKET_TEST_DB_PATH；"
                "禁止回退正式库（不会使用 MARKET_DB_PATH）"
            )
        resolved = Path(raw)
        prod = _env_value(_PROD_DB_ENV)
        if prod and _same_path(resolved, prod):
            raise ConfigError(
                "MARKET_TEST_DB_PATH 与 MARKET_DB_PATH 指向同一文件；"
                "正式库与测试库必须分离"
            )
        return resolved

    if env == "prod":
        raw = _env_value(_PROD_DB_ENV)
        if not raw:
            raise ConfigError(
                "未配置数据库路径：请显式传 --db 或设置 MARKET_DB_PATH；"
                "脚本不再回退相对路径默认值"
            )
        return Path(raw)

    raise ConfigError(f"未知环境：{env!r}；可选 ('prod', 'test')")


def enforce_research_2010_gate(
    db_path: str | Path,
    end: date | datetime | str,
    *,
    allow_post_2010: bool = False,
    action: str = "写入",
) -> None:
    """阻止把 2011+ 数据写进当前 2010 研究库。

    - 目标为 ``MARKET_DB_PATH`` 且 ``end > 2010-12-31``：无论是否带
      ``--allow-post-2010`` 都拒绝（flag 不作用于当前研究库）。
    - 其他目标（测试库、新版本库）：``end > 2010-12-31`` 需显式
      ``allow_post_2010=True``。

    Raises:
        ConfigError: 目标与 ``end`` 组合违反上述规则。
    """
    end_date = _as_date(end)
    if end_date <= RESEARCH_LAST_DATE:
        return

    prod = _env_value(_PROD_DB_ENV)
    if prod and _same_path(db_path, prod):
        raise ConfigError(
            f"拒绝{action}：目标为 MARKET_DB_PATH，end={end_date} 超过研究库截止 "
            f"{RESEARCH_LAST_DATE}。当前研究库只保留 2010；如需 2011+，"
            "请新建版本库并把 --db 指向新路径（--allow-post-2010 不适用于当前研究库）"
        )

    if not allow_post_2010:
        raise ConfigError(
            f"拒绝{action}：end={end_date} 超过研究库截止 {RESEARCH_LAST_DATE}。"
            "仅新库/新版本可显式加 --allow-post-2010"
        )
