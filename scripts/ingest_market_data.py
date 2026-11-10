#!/usr/bin/env python3
"""ingest_market_data.py — 把 Tushare 行情写入 ``market.duckdb``。

职责：
* 只写 ``market.duckdb``（warehouse 组件），不碰 backtest.duckdb；
* 采用 ``INSERT ... ON CONFLICT DO UPDATE``，可反复执行、行数不膨胀；
* 每张表的写入结果记录到 ``meta_ingest_log``。

示例：
    # 初始化 + 拉取交易日历、股票列表、20 只样本股、3 个指数、3 只宽基 ETF
    python scripts/ingest_market_data.py --db "$DUCKDB_PATH" \\
        --start 2015-01-01 --end 2026-11-06

    # 只补指定股票
    python scripts/ingest_market_data.py --stocks 600519.SH,000858.SZ

    # 额外尝试拉取指数成分权重（需要 Tushare index_weight 权限）
    python scripts/ingest_market_data.py --with-index-weight

注意：Tushare 的 ``fund_daily`` / ``index_weight`` 需要单独积分权限；
无权限时脚本会记录 warning 并跳过，不影响基础行情入库。
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import init_market_db as market
import polars as pl

from data_pipeline.core.errors import FetchError
from data_pipeline.sources.tushare_src import TushareSource

LOG = logging.getLogger("ingest_market_data")

DEFAULT_STOCKS: Final[tuple[str, ...]] = (
    "600519.SH",
    "000858.SZ",
    "600036.SH",
    "000001.SZ",
    "601318.SH",
    "600030.SH",
    "601166.SH",
    "600276.SH",
    "000333.SZ",
    "000651.SZ",
    "002415.SZ",
    "300750.SZ",
    "601012.SH",
    "600887.SH",
    "601888.SH",
    "600900.SH",
    "601398.SH",
    "601288.SH",
    "600028.SH",
    "601857.SH",
)
DEFAULT_INDEXES: Final[tuple[str, ...]] = ("000300.SH", "000905.SH", "000852.SH")
#: 默认只取 3 只宽基 ETF；没有 fund_daily 权限时会逐只 warning 并跳过。
DEFAULT_FUNDS: Final[tuple[str, ...]] = ("510300.SH", "510500.SH", "159915.SZ")
CORE_STOCKS: Final[tuple[str, ...]] = DEFAULT_STOCKS[:5]


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
def _table_columns(con, table: str) -> list[str]:
    return [str(row[0]) for row in con.execute(f'DESCRIBE "{table}"').fetchall()]


def upsert(con, table: str, frame: pl.DataFrame, keys: tuple[str, ...]) -> int:
    """把 polars DataFrame 幂等写入 DuckDB；返回写入行数。"""
    if frame is None or frame.is_empty():
        return 0

    columns = _table_columns(con, table)
    missing_keys = [key for key in keys if key not in frame.columns]
    if missing_keys:
        raise ValueError(f"{table} 缺少幂等键列：{missing_keys}")

    selected = [column for column in columns if column in frame.columns]
    frame = frame.select(selected).unique(subset=list(keys), keep="last")

    update_columns = [column for column in selected if column not in keys]
    if update_columns:
        assignments = ", ".join(
            f'"{column}" = excluded."{column}"' for column in update_columns
        )
        conflict = f"DO UPDATE SET {assignments}"
    else:
        conflict = "DO NOTHING"

    view_name = "_ingest_batch"
    con.register(view_name, frame)
    try:
        key_sql = ", ".join(f'"{key}"' for key in keys)
        # table / columns 均来自 information_schema 与 quant_schema 常量，无外部输入
        con.execute(
            f'INSERT INTO "{table}" BY NAME SELECT * FROM {view_name} '
            f"ON CONFLICT ({key_sql}) {conflict}"
        )
    finally:
        con.unregister(view_name)
    return frame.height


def log_ingest(
    con,
    table: str,
    scope: str,
    rows: int,
    status: str,
    started: datetime,
    detail: str | None = None,
) -> None:
    frame = pl.DataFrame(
        {
            "table_name": [table],
            "scope_key": [scope],
            "row_count": [rows],
            "status": [status],
            "detail": [detail],
            "started_at": [started],
            "finished_at": [datetime.now(UTC)],
        }
    )
    upsert(con, "meta_ingest_log", frame, ("table_name", "scope_key"))


# ---------------------------------------------------------------------------
# 各表摄入
# ---------------------------------------------------------------------------
def ingest_calendar(con, source: TushareSource, args) -> bool:
    """抓取交易日历；限频时返回 False，由调用方从日线推导。"""
    started = datetime.now(UTC)
    try:
        frame = source.fetch_trade_cal(
            args.start_compact, args.end_compact, args.calendar
        )
    except FetchError as exc:
        log_ingest(
            con,
            "dim_trade_cal",
            f"{args.calendar}:{args.start}:{args.end}",
            0,
            "failed",
            started,
            str(exc)[:500],
        )
        LOG.warning("交易日历接口不可用，稍后从日线推导：%s", exc)
        return False
    rows = upsert(con, "dim_trade_cal", frame, ("exchange", "cal_date"))
    log_ingest(
        con,
        "dim_trade_cal",
        f"{args.calendar}:{args.start}:{args.end}",
        rows,
        "ok",
        started,
    )
    LOG.info("交易日历：%d 行", rows)
    return True


def derive_calendar(con, args) -> None:
    """从 ``fact_daily`` 的实际交易日期反推交易日历（低积分 token 的降级路径）。"""
    started = datetime.now(UTC)
    con.execute(
        """
        INSERT INTO dim_trade_cal (exchange, cal_date, is_open, pretrade_date)
        SELECT ?, trade_date, TRUE,
               lag(trade_date) OVER (ORDER BY trade_date)
        FROM (
            SELECT DISTINCT trade_date
            FROM fact_daily
            WHERE trade_date BETWEEN ? AND ?
        )
        ON CONFLICT (exchange, cal_date) DO UPDATE SET
            is_open = excluded.is_open,
            pretrade_date = excluded.pretrade_date
        """,
        [args.calendar, args.start, args.end],
    )
    rows = int(
        con.execute(
            "SELECT count(*) FROM dim_trade_cal WHERE exchange = ?", [args.calendar]
        ).fetchall()[0][0]
    )
    log_ingest(
        con,
        "dim_trade_cal",
        f"{args.calendar}:derived:{args.start}:{args.end}",
        rows,
        "ok",
        started,
        "derived from fact_daily",
    )
    LOG.info("交易日历（由日线推导）：%d 行", rows)


def ingest_stock_basic(con, source: TushareSource) -> None:
    started = datetime.now(UTC)
    try:
        frame = source.fetch_stock_basic()
    except FetchError as exc:
        log_ingest(
            con, "dim_stock_basic", "all:listed", 0, "failed", started, str(exc)[:500]
        )
        LOG.warning("股票列表接口不可用，跳过（不影响日线）：%s", exc)
        return
    rows = upsert(con, "dim_stock_basic", frame, ("ts_code",))
    log_ingest(con, "dim_stock_basic", "all:listed", rows, "ok", started)
    LOG.info("股票列表：%d 行", rows)


def _ingest_stock(con, source: TushareSource, ts_code: str, args) -> None:
    """按表独立抓取，任一辅助表限频/无权限不阻断日线。"""
    scope = f"{ts_code}:{args.start}:{args.end}"

    def _write(
        table: str,
        fetch,
        *,
        keys: tuple[str, ...] = ("ts_code", "trade_date"),
    ) -> int | None:
        started = datetime.now(UTC)
        try:
            frame = fetch()
            rows = upsert(con, table, frame, keys)
        except FetchError as exc:
            log_ingest(con, table, scope, 0, "failed", started, str(exc)[:500])
            LOG.warning("%s %s 跳过：%s", ts_code, table, exc)
            return None
        log_ingest(con, table, scope, rows, "ok", started)
        if rows == 0:
            LOG.warning("%s %s 返回 0 行", ts_code, table)
        else:
            LOG.info("%s %s：%d 行", ts_code, table, rows)
        return rows

    daily_rows = _write(
        "fact_daily",
        lambda: source.fetch_daily(ts_code, args.start_compact, args.end_compact),
    )
    if daily_rows is None:
        return

    _write(
        "fact_adj_factor",
        lambda: source.fetch_adj_factor(ts_code, args.start_compact, args.end_compact),
    )

    want_basic = args.daily_basic == "all" or (
        args.daily_basic == "core" and ts_code in CORE_STOCKS
    )
    if want_basic:
        _write(
            "fact_daily_basic",
            lambda: source.fetch_daily_basic(
                ts_code, args.start_compact, args.end_compact
            ),
        )

    want_limit = args.stk_limit == "all" or (
        args.stk_limit == "core" and ts_code in CORE_STOCKS
    )
    if want_limit:
        _write(
            "fact_stk_limit",
            lambda: source.fetch_stk_limit(
                ts_code, args.start_compact, args.end_compact
            ),
        )


def ingest_indexes(con, source: TushareSource, args) -> None:
    for index_code in args.indexes:
        started = datetime.now(UTC)
        try:
            frame = source.fetch_index_daily(
                index_code, args.start_compact, args.end_compact
            )
            rows = upsert(con, "fact_index_daily", frame, ("index_code", "trade_date"))
            log_ingest(
                con,
                "fact_index_daily",
                f"{index_code}:{args.start}:{args.end}",
                rows,
                "ok",
                started,
            )
            LOG.info("指数 %s：%d 行", index_code, rows)
        except FetchError as exc:
            log_ingest(
                con,
                "fact_index_daily",
                f"{index_code}:{args.start}:{args.end}",
                0,
                "failed",
                started,
                str(exc)[:500],
            )
            LOG.warning("指数 %s 跳过：%s", index_code, exc)


def ingest_funds(con, source: TushareSource, args) -> None:
    for ts_code in args.funds:
        started = datetime.now(UTC)
        try:
            frame = source.fetch_fund_daily(
                ts_code, args.start_compact, args.end_compact
            )
            rows = upsert(con, "fact_fund_daily", frame, ("ts_code", "trade_date"))
            log_ingest(
                con,
                "fact_fund_daily",
                f"{ts_code}:{args.start}:{args.end}",
                rows,
                "ok",
                started,
            )
            LOG.info("ETF %s：%d 行", ts_code, rows)
        except FetchError as exc:
            log_ingest(
                con,
                "fact_fund_daily",
                f"{ts_code}:{args.start}:{args.end}",
                0,
                "failed",
                started,
                str(exc)[:500],
            )
            LOG.warning("ETF %s 跳过（通常是无 fund_daily 权限）：%s", ts_code, exc)


def ingest_index_weights(con, source: TushareSource, args) -> None:
    """按月频月末交易日抓取指数成分权重（需要 Tushare 权限）。"""
    dates = [
        str(row[0])
        for row in con.execute(
            "SELECT strftime(cal_date, '%Y%m%d') FROM dim_trade_cal "
            "WHERE exchange = ? AND is_open = TRUE AND cal_date BETWEEN ? AND ? "
            "ORDER BY cal_date",
            [args.calendar, args.start, args.end],
        ).fetchall()
    ]
    # 只取每月最后一个交易日
    month_last: dict[str, str] = {}
    for compact in dates:
        month_last[compact[:6]] = compact
    for index_code in args.indexes:
        for compact in month_last.values():
            started = datetime.now(UTC)
            try:
                frame = source.fetch_index_weight(index_code, compact)
            except FetchError as exc:
                log_ingest(
                    con,
                    "fact_index_weight",
                    f"{index_code}:{compact}",
                    0,
                    "failed",
                    started,
                    str(exc)[:500],
                )
                LOG.warning(
                    "指数权重 %s@%s 跳过（通常是无 index_weight 权限）：%s",
                    index_code,
                    compact,
                    exc,
                )
                return
            if "index_code" not in frame.columns:
                frame = frame.with_columns(pl.lit(index_code).alias("index_code"))
            frame = frame.with_columns(
                pl.lit(compact).str.strptime(pl.Date, "%Y%m%d").alias("trade_date")
            )
            rows = upsert(
                con,
                "fact_index_weight",
                frame,
                ("index_code", "trade_date", "con_code"),
            )
            log_ingest(
                con,
                "fact_index_weight",
                f"{index_code}:{compact}",
                rows,
                "ok",
                started,
            )
            LOG.info("指数权重 %s@%s：%d 行", index_code, compact, rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest_market_data.py",
        description="Tushare -> market.duckdb 增量/回补（幂等）",
    )
    parser.add_argument("--db", type=Path, default=market.DEFAULT_DB_PATH)
    parser.add_argument("--start", default="2015-01-01", help="YYYY-MM-DD")
    parser.add_argument("--end", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--calendar", default="SSE")
    parser.add_argument(
        "--stocks",
        default=",".join(DEFAULT_STOCKS),
        help="逗号分隔的 ts_code；传空字符串则跳过个股",
    )
    parser.add_argument(
        "--indexes", default=",".join(DEFAULT_INDEXES), help="逗号分隔的指数代码"
    )
    parser.add_argument(
        "--funds", default=",".join(DEFAULT_FUNDS), help="逗号分隔的 ETF 代码"
    )
    parser.add_argument(
        "--daily-basic",
        choices=("all", "core", "none"),
        default="core",
        help="daily_basic 抓取范围：all=全部股票，core=前 5 只核心票，none=跳过",
    )
    parser.add_argument(
        "--stk-limit",
        dest="stk_limit",
        choices=("all", "core", "none"),
        default="all",
        help="stk_limit 抓取范围：all=全部股票，core=前 5 只核心票，none=跳过",
    )
    parser.add_argument(
        "--with-index-weight",
        action="store_true",
        help="额外抓取指数成分权重（需要 Tushare 权限）",
    )
    parser.add_argument("--threads", type=int, default=market.DEFAULT_THREADS)
    parser.add_argument(
        "--memory-limit", dest="memory_limit", default=market.DEFAULT_MEMORY_LIMIT
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.log_level)

    args.start_compact = date.fromisoformat(args.start).strftime("%Y%m%d")
    args.end_compact = date.fromisoformat(args.end).strftime("%Y%m%d")
    args.stocks = tuple(code.strip() for code in args.stocks.split(",") if code.strip())
    args.indexes = tuple(
        code.strip() for code in args.indexes.split(",") if code.strip()
    )
    args.funds = tuple(code.strip() for code in args.funds.split(",") if code.strip())

    try:
        source = TushareSource()
        with market.database(
            args.db, threads=args.threads, memory_limit=args.memory_limit
        ) as con:
            market.init_schema(con)
            calendar_ok = ingest_calendar(con, source, args)
            ingest_stock_basic(con, source)
            for ts_code in args.stocks:
                _ingest_stock(con, source, ts_code, args)
            if not calendar_ok:
                derive_calendar(con, args)
            ingest_indexes(con, source, args)
            if args.funds:
                ingest_funds(con, source, args)
            if args.with_index_weight:
                ingest_index_weights(con, source, args)
            LOG.info("完成：db=%s version=%s", args.db, market.installed_version(con))
    except market.ConfigError as exc:
        LOG.error("配置错误：%s", exc)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI 顶层统一转为退出码
        LOG.error("摄入失败：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
