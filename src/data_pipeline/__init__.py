"""data_pipeline — market.duckdb 的初始化、行情摄入与共享连接。"""

from __future__ import annotations


def main() -> None:
    """控制台入口：提示使用 scripts/ 下的可执行脚本。"""
    print(
        "quant-data-pipeline: use\n"
        "  python scripts/init_market_db.py\n"
        "  python scripts/init_factor_db.py\n"
        "  python scripts/ingest_market_data.py"
    )


__all__ = ["main"]
