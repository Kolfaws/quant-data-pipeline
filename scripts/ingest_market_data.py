#!/usr/bin/env python3
"""ingest_market_data.py — 把 Tushare 行情写入 ``market.duckdb``。

职责：
* 只写 ``market.duckdb``（warehouse 组件），不碰 backtest.duckdb；
* 采用 ``INSERT ... ON CONFLICT DO UPDATE``，可反复执行、行数不膨胀；
* 每张表的写入结果记录到 ``meta_ingest_log``；
* 整批摄入共用一个事务：数据与 ``meta_ingest_log`` 同事务提交/回滚，
  中断或 ``duckdb.Error`` 不会留下“部分表已写、无记录”的状态。

写入闸门：
* 默认区间是 2010-01-01..2010-12-31（当前研究库只保留 2010）；
* 目标为 ``MARKET_DB_PATH`` 且 ``end > 2010-12-31`` 时 fail-fast；
* ``--allow-post-2010`` 只用于新库/新版本，不能解锁当前研究库。

示例：
    # 默认只摄入 2010；当前研究库请显式传 2010 区间
    python scripts/ingest_market_data.py --db "${MARKET_DB_PATH}" \\
        --start 2010-01-01 --end 2010-12-31

    # 只补指定股票
    python scripts/ingest_market_data.py --stocks 600519.SH,000858.SZ

    # 新库/新版本写 2011+：必须显式 --allow-post-2010，且 --db 不能是研究库
    python scripts/ingest_market_data.py --db "$MARKET_TEST_DB_PATH" \\
        --start 2011-01-01 --end 2011-12-31 --allow-post-2010

    # 额外尝试拉取指数成分权重（需要 Tushare index_weight 权限）
    python scripts/ingest_market_data.py --with-index-weight

注意：Tushare 的 ``fund_daily`` / ``index_weight`` 需要单独积分权限；
无权限时脚本会记录 warning 并跳过，不影响基础行情入库。
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import init_market_db as market
import polars as pl

from data_pipeline.core.errors import FetchError
from data_pipeline.guards import enforce_research_2010_gate, require_market_db_path
from data_pipeline.sources.tushare_src import TushareSource

LOG = logging.getLogger("ingest_market_data")

#: 当前 2010 研究库的默认摄入区间（含端点）。
DEFAULT_START: Final[str] = "2010-01-01"
DEFAULT_END: Final[str] = "2010-12-31"
#: 批次汇总日志写在 ``meta_ingest_log`` 的伪表名。
BATCH_TABLE: Final[str] = "ingest_batch"


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
# 批次
# ---------------------------------------------------------------------------
@dataclass
class IngestBatch:
    """一次摄入运行的批次上下文；``batch_id`` 会写进每条日志的 detail。"""

    batch_id: str
    start: str
    end: str
    row_count: int = 0

    @classmethod
    def new(cls, *, start: str, end: str) -> IngestBatch:
        return cls(batch_id=uuid.uuid4().hex, start=start, end=end)

    @property
    def scope(self) -> str:
        return f"{self.start}:{self.end}"

    def detail(self, detail: str | None = None) -> str:
        prefix = f"batch_id={self.batch_id}"
        return f"{prefix}; {detail}" if detail else prefix


def batch_of(args) -> IngestBatch | None:
    """从 argparse/SimpleNamespace 取批次上下文；直接调内部函数时可为 None。"""
    return getattr(args, "batch", None)


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
        try:
            con.unregister(view_name)
        except Exception as exc:  # noqa: BLE001 - 事务已 aborted 时不能掩盖原始写入异常
            LOG.debug("unregister %s 失败（事务可能已回滚）：%s", view_name, exc)
    return frame.height


def log_ingest(
    con,
    table: str,
    scope: str,
    rows: int,
    status: str,
    started: datetime,
    detail: str | None = None,
    *,
    batch: IngestBatch | None = None,
) -> None:
    """写一条 ``meta_ingest_log``；调用方负责事务边界。

    ``batch`` 不为空时 detail 前缀 ``batch_id=<id>``，并累计批次成功行数。
    """
    if batch is not None:
        detail = batch.detail(detail)
        if status == "ok":
            batch.row_count += rows
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


def log_batch(
    con,
    batch: IngestBatch,
    *,
    status: str,
    started: datetime,
    rows: int = 0,
    detail: str | None = None,
) -> None:
    """写批次汇总行（伪表 ``ingest_batch``），与数据同事务。"""
    log_ingest(
        con,
        BATCH_TABLE,
        batch.scope,
        rows,
        status,
        started,
        batch.detail(detail),
        batch=None,  # 汇总行不再参与行数累计
    )


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
            batch=batch_of(args),
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
        batch=batch_of(args),
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
        batch=batch_of(args),
    )
    LOG.info("交易日历（由日线推导）：%d 行", rows)


def ingest_stock_basic(con, source: TushareSource, args) -> None:
    """摄入股票列表。

    只取 ``list_status='L'``：退市股不在 ``dim_stock_basic``，历史股票池存在
    幸存者偏差；默认样本股也是当前大票，不是 2010 PIT 股票池。需要历史池时
    另行补退市/成分数据，不要用当前名单回填历史。
    """
    started = datetime.now(UTC)
    try:
        frame = source.fetch_stock_basic()
    except FetchError as exc:
        log_ingest(
            con,
            "dim_stock_basic",
            "all:listed",
            0,
            "failed",
            started,
            str(exc)[:500],
            batch=batch_of(args),
        )
        LOG.warning("股票列表接口不可用，跳过（不影响日线）：%s", exc)
        return
    rows = upsert(con, "dim_stock_basic", frame, ("ts_code",))
    log_ingest(
        con,
        "dim_stock_basic",
        "all:listed",
        rows,
        "ok",
        started,
        batch=batch_of(args),
    )
    LOG.info("股票列表：%d 行", rows)
    LOG.warning(
        "dim_stock_basic 只含 list_status='L'；退市股/历史成分未覆盖，"
        "历史股票池需另行 PIT 处理"
    )


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
            log_ingest(
                con,
                table,
                scope,
                0,
                "failed",
                started,
                str(exc)[:500],
                batch=batch_of(args),
            )
            LOG.warning("%s %s 跳过：%s", ts_code, table, exc)
            return None
        log_ingest(con, table, scope, rows, "ok", started, batch=batch_of(args))
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
                batch=batch_of(args),
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
                batch=batch_of(args),
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
                batch=batch_of(args),
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
                batch=batch_of(args),
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
                    batch=batch_of(args),
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
                batch=batch_of(args),
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
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="market.duckdb 路径；缺省读 MARKET_DB_PATH，未配置则报错（无相对路径回退）",
    )
    parser.add_argument("--start", default=DEFAULT_START, help="YYYY-MM-DD")
    parser.add_argument(
        "--end",
        default=DEFAULT_END,
        help="YYYY-MM-DD；默认 2010-12-31，写 2011+ 需新库并显式 --allow-post-2010",
    )
    parser.add_argument(
        "--allow-post-2010",
        action="store_true",
        help="仅新库/新版本：允许 end>2010-12-31；不作用于 MARKET_DB_PATH 研究库",
    )
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


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]


def _rollback_quiet(con) -> None:
    try:
        con.execute("ROLLBACK")
    except Exception as exc:  # noqa: BLE001 - 可能已自动回滚或连接已失效
        LOG.debug("回滚时无活动事务或回滚失败：%s", exc)


def _record_failed_batch(
    con,
    batch: IngestBatch,
    started: datetime,
    exc: BaseException,
) -> None:
    """回滚后单独提交一条 failed 批次日志，保证“中断/报错有记录”。"""
    try:
        con.execute("BEGIN TRANSACTION")
        log_batch(
            con,
            batch,
            status="failed",
            started=started,
            rows=0,
            detail=_error_text(exc),
        )
        con.execute("COMMIT")
    except Exception as log_exc:  # noqa: BLE001 - 不能掩盖原始异常
        _rollback_quiet(con)
        LOG.error("写 failed 批次日志失败：%s", log_exc)


def run_ingest(con, source, args) -> IngestBatch:
    """执行一次完整摄入：整批一个事务，数据与 ``meta_ingest_log`` 同提交。

    * 单表 ``FetchError`` 属于预期降级：事务内记 failed 后继续；
    * 其他异常（含 ``duckdb.Error``、``KeyboardInterrupt``）：整批回滚，
      再单独写一条 failed 批次日志，然后原样抛出；
    * 不会留下“部分表已写、无记录”的状态。
    """
    batch: IngestBatch | None = getattr(args, "batch", None)
    if batch is None:
        batch = IngestBatch.new(start=args.start, end=args.end)
        args.batch = batch
    started = datetime.now(UTC)

    con.execute("BEGIN TRANSACTION")
    try:
        calendar_ok = ingest_calendar(con, source, args)
        ingest_stock_basic(con, source, args)
        for ts_code in args.stocks:
            _ingest_stock(con, source, ts_code, args)
        if not calendar_ok:
            derive_calendar(con, args)
        ingest_indexes(con, source, args)
        if args.funds:
            ingest_funds(con, source, args)
        if args.with_index_weight:
            ingest_index_weights(con, source, args)
        log_batch(con, batch, status="ok", started=started, rows=batch.row_count)
        con.execute("COMMIT")
        return batch
    except BaseException as exc:
        _rollback_quiet(con)
        _record_failed_batch(con, batch, started, exc)
        raise


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.log_level)

    try:
        args.start_compact = date.fromisoformat(args.start).strftime("%Y%m%d")
        args.end_compact = date.fromisoformat(args.end).strftime("%Y%m%d")
    except ValueError as exc:
        LOG.error("日期参数非法（要求 YYYY-MM-DD）：%s", exc)
        return 2
    args.stocks = tuple(code.strip() for code in args.stocks.split(",") if code.strip())
    args.indexes = tuple(
        code.strip() for code in args.indexes.split(",") if code.strip()
    )
    args.funds = tuple(code.strip() for code in args.funds.split(",") if code.strip())

    try:
        db_path = require_market_db_path(args.db)
        # fail-fast：先过写入闸门，再建连接/构造 Tushare 客户端。
        enforce_research_2010_gate(
            db_path,
            args.end,
            allow_post_2010=args.allow_post_2010,
        )
        batch = IngestBatch.new(start=args.start, end=args.end)
        args.batch = batch
        source = TushareSource()
        with market.database(
            db_path, threads=args.threads, memory_limit=args.memory_limit
        ) as con:
            market.init_schema(con)
            run_ingest(con, source, args)
            LOG.info(
                "完成：db=%s version=%s batch_id=%s",
                db_path,
                market.installed_version(con),
                batch.batch_id,
            )
    except market.ConfigError as exc:
        LOG.error("配置错误：%s", exc)
        return 2
    except Exception as exc:  # noqa: BLE001 - CLI 顶层统一转为退出码
        LOG.error("摄入失败：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
