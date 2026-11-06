"""data_pipeline.core.errors — 管道层领域异常。"""

from __future__ import annotations


class DataPipelineError(RuntimeError):
    """数据管道异常基类。"""


class ConfigError(DataPipelineError, ValueError):
    """配置缺失或非法。"""


class FetchError(DataPipelineError):
    """数据源拉取失败（网络、限流、权限、空数据）。"""


class DBWriteError(DataPipelineError):
    """写库失败（约束冲突、事务回滚）。"""


__all__ = ["ConfigError", "DBWriteError", "DataPipelineError", "FetchError"]
