"""data_pipeline.config — 极简环境变量加载。

不依赖 python-dotenv：

1. 读取项目根目录 ``.env``（若存在），只填充**尚未设置**的环境变量；
2. 真实环境变量优先级高于 ``.env``；
3. 数据库路径只从环境变量读取；未设置时**不回退**相对路径默认值，
   由 :func:`data_pipeline.guards.require_market_db_path` 显式报错。
   代码中不写死任何机器绝对路径或 Token。
"""

from __future__ import annotations

import os
from pathlib import Path

from data_pipeline.environment import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """把 ``.env`` 中的 KEY=VALUE 写入 os.environ（不覆盖已有环境变量）。"""
    for key, value in dotenv_values(path or (PROJECT_ROOT / ".env")).items():
        os.environ.setdefault(key, value)


load_dotenv()

TUSHARE_TOKEN: str | None = os.getenv("TUSHARE_TOKEN") or None
MARKET_DB_PATH: str | None = os.getenv("MARKET_DB_PATH") or os.getenv("DUCKDB_PATH")
MARKET_TEST_DB_PATH: str | None = os.getenv("MARKET_TEST_DB_PATH") or os.getenv(
    "DUCKDB_TEST_PATH"
)
# 兼容既有代码：默认指正式库
DUCKDB_PATH: str | None = MARKET_DB_PATH
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


def market_db_path(env: str = "prod") -> str | None:
    """返回指定环境的 market.duckdb 路径；未配置返回 None。"""
    if env not in ("prod", "test"):
        raise ValueError(f"未知环境：{env!r}；可选 ('prod', 'test')")
    return MARKET_TEST_DB_PATH if env == "test" else MARKET_DB_PATH


__all__ = [
    "DUCKDB_PATH",
    "LOG_LEVEL",
    "MARKET_DB_PATH",
    "MARKET_TEST_DB_PATH",
    "PROJECT_ROOT",
    "TUSHARE_TOKEN",
    "load_dotenv",
    "market_db_path",
]
