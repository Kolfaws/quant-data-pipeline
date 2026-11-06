"""data_pipeline.logger — 标准库 logging 配置（不引入 loguru 依赖）。"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """配置根 logger；重复调用是幂等的。"""
    global _CONFIGURED
    if _CONFIGURED:
        logging.getLogger().setLevel(getattr(logging, level.upper(), logging.INFO))
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s | %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


__all__ = ["get_logger", "setup_logging"]
