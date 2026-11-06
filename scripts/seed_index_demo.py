#!/usr/bin/env python3
"""seed_index_demo.py — 演示用指数行情补齐（Eastmoney 公开 K 线接口）。

**这不是生产数据源的替代品。**
生产路径始终是 ``ingest_market_data.py``（Tushare ``index_daily``）。
当 Tushare token 没有 ``index_daily`` 权限时，用本脚本把几个宽基指数补进
``market.duckdb``，以便跑通 quant-baseline 的外部指数基准。

写入表：``fact_index_daily``（主键 ``index_code, trade_date``，幂等 upsert）。

用法：
    python scripts/seed_index_demo.py --db "$DUCKDB_PATH" \\
        --start 2015-01-01 --end 2026-11-06
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import init_market_db as market
import polars as pl
import requests

LOG = logging.getLogger("seed_index_demo")

DEFAULT_INDEXES: tuple[str, ...] = ("000300.SH", "000905.SH", "000852.SH")

_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _secid(code: str) -> str:
    number, exchange = code.split(".", 1)
    return f"{1 if exchange.upper() == 'SH' else 0}.{number}"


def fetch_index(code: str, start: str, end: str) -> pl.DataFrame:
    response = requests.get(
        _URL,
        params={
            "secid": _secid(code),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "0",
            "beg": start.replace("-", ""),
            "end": end.replace("-", ""),
            "lmt": "10000",
        },
        headers=_HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or {}
    klines = data.get("klines") or []
    if not klines:
        raise RuntimeError(f"Eastmoney 未返回 {code} 的 K 线")

    rows = []
    for line in klines:
        parts = line.split(",")
        day, open_, close, high, low, volume, amount, _amp, pct_chg, chg, _turn = parts
        rows.append(
            {
                "index_code": code,
                "trade_date": date.fromisoformat(day),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "pre_close": float(close) - float(chg),
                "chg": float(chg),
                "pct_chg": float(pct_chg),
                "vol": float(volume),
                "amount": float(amount),
            }
        )
    frame = pl.DataFrame(rows).sort("trade_date")
    # 用前一日收盘修正 pre_close（比 close - chg 更稳）
    frame = frame.with_columns(
        pl.when(pl.col("pre_close").is_null())
        .then(pl.col("close").shift(1))
        .otherwise(pl.col("pre_close"))
        .alias("pre_close")
    )
    return frame


def upsert(con, table: str, frame: pl.DataFrame, keys: tuple[str, ...]) -> int:
    if frame.is_empty():
        return 0
    columns = [str(row[0]) for row in con.execute(f'DESCRIBE "{table}"').fetchall()]
    selected = [column for column in columns if column in frame.columns]
    frame = frame.select(selected).unique(subset=list(keys), keep="last")
    update_columns = [column for column in selected if column not in keys]
    conflict = (
        "DO UPDATE SET "
        + ", ".join(f'"{column}" = excluded."{column}"' for column in update_columns)
        if update_columns
        else "DO NOTHING"
    )
    key_sql = ", ".join(f'"{key}"' for key in keys)
    con.register("_seed_index", frame)
    try:
        con.execute(
            f'INSERT INTO "{table}" BY NAME SELECT * FROM _seed_index '
            f"ON CONFLICT ({key_sql}) {conflict}"
        )
    finally:
        con.unregister("_seed_index")
    return frame.height


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="seed_index_demo.py")
    parser.add_argument("--db", type=Path, default=market.DEFAULT_DB_PATH)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--indexes", default=",".join(DEFAULT_INDEXES))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s | %(message)s",
    )

    indexes = [item.strip() for item in args.indexes.split(",") if item.strip()]
    try:
        with market.database(args.db) as con:
            market.init_schema(con)
            for code in indexes:
                frame = fetch_index(code, args.start, args.end)
                rows = upsert(
                    con, "fact_index_daily", frame, ("index_code", "trade_date")
                )
                LOG.info(
                    "%s: %d 行（%s..%s）",
                    code,
                    rows,
                    frame["trade_date"][0],
                    frame["trade_date"][-1],
                )
            LOG.info("完成：db=%s version=%s", args.db, market.installed_version(con))
    except Exception as exc:  # noqa: BLE001
        LOG.error("失败：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
