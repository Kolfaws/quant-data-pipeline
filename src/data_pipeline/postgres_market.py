"""Collect and publish bounded Tushare market batches to PostgreSQL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl
from psycopg import Connection, Rollback
from psycopg.types.json import Jsonb
from quant_schema.postgres_ddl import (
    ADJUSTMENT,
    CALENDAR,
    DAILY,
    DATASETS,
    FACTOR_DEFINITION,
    FACTOR_VALUE,
    INSTRUMENT,
    POSTGRES_DDL,
    POSTGRES_VERSION,
    PUBLICATION,
    STOCK,
    Dataset,
)

from data_pipeline.sources.tushare_src import TushareSource

EXCHANGES = {"SSE": ".SH", "SZSE": ".SZ"}
SOURCE_LIMIT = 6000
SCHEMA_COMPONENT = "a_share_daily"
PUBLICATION_LOCK = 811402986858541052
MARKET_RELATIONS = {PUBLICATION, INSTRUMENT, FACTOR_DEFINITION, FACTOR_VALUE} | {
    dataset.table for dataset in DATASETS
}


class BatchError(ValueError):
    """A batch does not meet the publication contract."""


@dataclass(frozen=True)
class MarketBatch:
    start: date
    end: date
    observed_at: datetime
    frames: dict[Dataset, pl.DataFrame]

    def digest(self) -> str:
        digest = hashlib.sha256()
        for dataset in DATASETS:
            digest.update(dataset.table.encode())
            for row in self.frames[dataset].iter_rows():
                digest.update(json.dumps(row, default=str, allow_nan=False).encode())
                digest.update(b"\n")
        return digest.hexdigest()


def _checked(frame: pl.DataFrame, dataset: Dataset) -> pl.DataFrame:
    if missing := set(dataset.names) - set(frame.columns):
        raise BatchError(f"{dataset.table} missing columns {sorted(missing)}")
    frame = frame.select(dataset.names)
    if frame.height >= SOURCE_LIMIT:
        raise BatchError(f"{dataset.table} reached the source row limit")
    required = [name for name, kind in dataset.columns if kind.endswith("NOT NULL")]
    if frame.filter(pl.any_horizontal(pl.col(required).is_null())).height:
        raise BatchError(f"{dataset.table} has missing required values")
    numeric = [
        name
        for name, kind in dataset.columns
        if kind.startswith(("double precision", "numeric"))
    ]
    if (
        numeric
        and frame.filter(
            pl.any_horizontal(~pl.col(numeric).cast(pl.Float64).is_finite())
        ).height
    ):
        raise BatchError(f"{dataset.table} has nonfinite values")
    if frame.select(dataset.key).is_duplicated().any():
        raise BatchError(f"{dataset.table} has duplicate business keys")
    return frame


def collect_market(source: TushareSource, start: date, end: date) -> MarketBatch:
    """Fetch a bounded daily batch with no database write or calendar fallback."""
    if end < start or (end - start).days >= 31:
        raise BatchError("Choose an inclusive range of one to 31 calendar days")
    if end >= datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise BatchError("Only finished calendar days are eligible for publication")
    days = {start + timedelta(days=i) for i in range((end - start).days + 1)}
    calendars = []
    stocks = []
    for exchange in EXCHANGES:
        calendar = _checked(
            source.fetch_trade_cal(
                start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), exchange
            ),
            CALENDAR,
        )
        if set(calendar["exchange"]) != {exchange} or set(calendar["cal_date"]) != days:
            raise BatchError(f"Incomplete or unexpected {exchange} calendar")
        calendars.append(calendar)
        for status in ("L", "D", "P"):
            frame = source.fetch_stock_snapshot(exchange, status)
            if frame.is_empty() and status == "P":
                continue
            frame = _checked(frame, STOCK)
            if (
                frame.is_empty()
                or set(frame["exchange"]) != {exchange}
                or set(frame["list_status"]) != {status}
            ):
                raise BatchError(
                    f"Incomplete or unexpected {exchange} stock class {status}"
                )
            stocks.append(frame)
    stock = pl.concat(stocks, how="vertical_relaxed")
    if stock.select(STOCK.key).is_duplicated().any():
        raise BatchError("Stock classes contain overlapping codes")
    calendar = pl.concat(calendars, how="vertical_relaxed")
    open_sets = {
        exchange: set(
            calendar.filter((pl.col("exchange") == exchange) & pl.col("is_open"))[
                "cal_date"
            ]
        )
        for exchange in EXCHANGES
    }
    bars, adjustments = [], []
    for day in sorted(set.union(*open_sets.values())):
        compact = day.strftime("%Y%m%d")
        suffixes = [
            suffix
            for exchange, suffix in EXCHANGES.items()
            if day in open_sets[exchange]
        ]
        raw_bars = _checked(source.fetch_daily_cross_section(compact), DAILY)
        raw_adj = _checked(source.fetch_adjustment_cross_section(compact), ADJUSTMENT)
        if set(raw_bars["trade_date"]) != {day} or set(raw_adj["trade_date"]) != {day}:
            raise BatchError(f"Incomplete or unexpected market data for {day}")
        bar = raw_bars.filter(
            pl.any_horizontal([pl.col("ts_code").str.ends_with(s) for s in suffixes])
        )
        if any(not bar["ts_code"].str.ends_with(suffix).any() for suffix in suffixes):
            raise BatchError(f"An open exchange has no daily bars on {day}")
        joined = bar.select("ts_code").join(
            stock.select("ts_code", "list_date", "delist_date"),
            on="ts_code",
            how="inner",
        )
        if joined.filter(
            (pl.col("list_date") > day) | (pl.col("delist_date") < day)
        ).height:
            raise BatchError(
                f"Stock code has bars outside its known listing history for {day}"
            )
        adj = raw_adj.join(bar.select(DAILY.key), on=DAILY.key, how="semi")
        if adj.height != bar.height:
            raise BatchError(f"Some daily bars have no adjustment factor on {day}")
        # Normalize money to the storage scale before hashing or conflict comparison.
        bar = bar.with_columns(pl.col("amount").cast(pl.String).cast(pl.Decimal(20, 4)))
        bars.append(bar)
        adjustments.append(adj)
    frames = {STOCK: stock, CALENDAR: calendar}
    for dataset, pieces in ((DAILY, bars), (ADJUSTMENT, adjustments)):
        frames[dataset] = (
            pl.concat(pieces, how="vertical_relaxed")
            if pieces
            else pl.DataFrame(schema={name: pl.Null for name in dataset.names})
        )
    return MarketBatch(
        start,
        end,
        datetime.now(UTC),
        {dataset: frame.sort(dataset.key) for dataset, frame in frames.items()},
    )


def init_postgres(connection: Connection[Any]) -> None:
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (PUBLICATION_LOCK,))
        version_table = connection.execute(
            "SELECT to_regclass('control.schema_version')"
        ).fetchone()
        if version_table and version_table[0] is not None:
            version = connection.execute(
                "SELECT version FROM control.schema_version WHERE component = %s",
                (SCHEMA_COMPONENT,),
            ).fetchone()
            if version is not None:
                check_version(connection)
                return
        if _registered_relations(connection):
            raise BatchError(
                "Unversioned PostgreSQL relations already exist; inspect them before initialization"
            )
        for statement in POSTGRES_DDL:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO control.schema_version VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (SCHEMA_COMPONENT, POSTGRES_VERSION),
        )
        check_version(connection)


def check_version(connection: Connection[Any]) -> None:
    version = connection.execute(
        "SELECT version FROM control.schema_version WHERE component = %s",
        (SCHEMA_COMPONENT,),
    ).fetchone()
    if version != (POSTGRES_VERSION,):
        raise BatchError("PostgreSQL market schema version does not match the pipeline")
    if _registered_relations(connection) != MARKET_RELATIONS:
        raise BatchError("PostgreSQL market schema is missing required relations")


def _registered_relations(connection: Connection[Any]) -> set[str]:
    return {
        name
        for (name,) in connection.execute(
            "SELECT name FROM unnest(%s::text[]) AS relations(name) WHERE to_regclass(name) IS NOT NULL",
            (sorted(MARKET_RELATIONS),),
        )
    }


def publish_market(
    connection: Connection[Any], batch: MarketBatch
) -> tuple[int, dict[str, int]]:
    """COPY validated rows to transaction-local staging, then publish atomically."""
    digest = batch.digest()
    with connection.transaction() as transaction:
        check_version(connection)
        for dataset in DATASETS:
            stage = f"pg_temp.stage_{dataset.table.split('.')[1]}"
            names = ", ".join(dataset.names)
            definitions = ", ".join(f"{name} {kind}" for name, kind in dataset.columns)
            keys = ", ".join(dataset.key)
            connection.execute(
                f"CREATE TEMP TABLE {stage} ({definitions}, PRIMARY KEY ({keys})) ON COMMIT DROP"
            )
            with (
                connection.cursor() as cursor,
                cursor.copy(f"COPY {stage} ({names}) FROM STDIN") as copy,
            ):
                for row in batch.frames[dataset].iter_rows():
                    copy.write_row(row)
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (PUBLICATION_LOCK,))
        observed = connection.execute(
            f"SELECT version_id, counts FROM {PUBLICATION} WHERE source = 'tushare' "
            "AND start_date = %s AND end_date = %s AND content_sha256 = %s "
            "AND observed_at = %s ORDER BY version_id DESC LIMIT 1",
            (batch.start, batch.end, digest, batch.observed_at),
        ).fetchone()
        if observed is not None:
            return observed[0], {name: 0 for name in observed[1]}
        latest_publication = connection.execute(
            f"SELECT version_id, observed_at FROM {PUBLICATION} WHERE source = 'tushare' ORDER BY version_id DESC LIMIT 1"
        ).fetchone()
        if latest_publication is not None and batch.observed_at < latest_publication[1]:
            raise BatchError(
                "A newer Tushare snapshot was published; recollect before retrying"
            )
        version_row = connection.execute(
            f"INSERT INTO {PUBLICATION} (source, observed_at, start_date, end_date, content_sha256, counts) "
            "VALUES ('tushare', %s, %s, %s, %s, '{}'::jsonb) RETURNING version_id",
            (batch.observed_at, batch.start, batch.end, digest),
        ).fetchone()
        assert version_row is not None
        version = version_row[0]
        connection.execute(
            f"INSERT INTO {INSTRUMENT} (ts_code) "
            "SELECT ts_code FROM pg_temp.stage_stock_snapshot "
            "UNION SELECT ts_code FROM pg_temp.stage_stock_daily ON CONFLICT DO NOTHING"
        )
        counts = {}
        for dataset in DATASETS:
            stage = f"pg_temp.stage_{dataset.table.split('.')[1]}"
            names = ", ".join(dataset.names)
            keys = ", ".join(dataset.key)
            values = tuple(name for name in dataset.names if name not in dataset.key)
            unequal = " OR ".join(
                f"s.{name} IS DISTINCT FROM t.{name}" for name in values
            )
            if dataset == STOCK:
                latest = f"SELECT DISTINCT ON (ts_code) {names} FROM {dataset.table} ORDER BY ts_code, version_id DESC"
                result = connection.execute(
                    f"INSERT INTO {dataset.table} ({names}, version_id) "
                    f"SELECT {', '.join(f's.{name}' for name in dataset.names)}, %s FROM {stage} s "
                    f"LEFT JOIN ({latest}) t USING (ts_code) WHERE t.ts_code IS NULL OR {unequal}",
                    (version,),
                )
            else:
                conflict = connection.execute(
                    f"SELECT 1 FROM {stage} s JOIN {dataset.table} t USING ({keys}) WHERE {unequal} LIMIT 1"
                ).fetchone()
                if conflict:
                    raise BatchError(
                        f"Historical change in {dataset.table} requires review before publication"
                    )
                result = connection.execute(
                    f"INSERT INTO {dataset.table} ({names}, version_id) SELECT {names}, %s FROM {stage} "
                    f"ON CONFLICT ({keys}) DO NOTHING",
                    (version,),
                )
            counts[dataset.table] = result.rowcount
        if latest_publication is not None and not any(counts.values()):
            version = latest_publication[0]
            raise Rollback(transaction)
        connection.execute(
            f"UPDATE {PUBLICATION} SET counts = %s WHERE version_id = %s",
            (Jsonb(counts), version),
        )
    return version, counts
