"""Export bounded, versioned PostgreSQL inputs for DuckDB research."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from psycopg import Connection
from quant_schema import constants as names
from quant_schema.postgres_ddl import ADJUSTMENT, CALENDAR, DAILY, PUBLICATION, STOCK

from data_pipeline.postgres_market import EXCHANGES, BatchError, check_version

EXPORTS = {
    names.DIM_STOCK_BASIC: STOCK,
    names.DIM_TRADE_CAL: CALENDAR,
    names.FACT_DAILY: DAILY,
    names.FACT_ADJ_FACTOR: ADJUSTMENT,
}
ARROW_TYPES = {
    "text": pa.string(),
    "date": pa.date32(),
    "boolean": pa.bool_(),
    "double precision": pa.float64(),
    "numeric(20,4)": pa.decimal128(20, 4),
}


def export_research(
    connection: Connection[Any],
    destination: Path,
    *,
    start: date,
    end: date,
    codes: list[str],
    version: int | None = None,
) -> dict[str, Any]:
    if start > end or (version is not None and version < 1):
        raise BatchError("Invalid research date range or publication version")
    if destination.exists():
        raise BatchError("Research output already exists; use a new directory")
    with TemporaryDirectory(
        prefix="quant-export-", dir=destination.parent
    ) as directory:
        staging = Path(directory) / "snapshot"
        staging.mkdir()
        with connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            check_version(connection)
            publication = connection.execute(
                f"SELECT version_id, observed_at FROM {PUBLICATION} "
                "WHERE (%s::bigint IS NULL OR version_id = %s) ORDER BY version_id DESC LIMIT 1",
                (version, version),
            ).fetchone()
            if publication is None:
                raise BatchError("Requested publication version does not exist")
            version, observed_at = publication
            coverage = connection.execute(
                f"SELECT count(*), count(*) FILTER (WHERE is_open) FROM {CALENDAR.table} "
                "WHERE version_id <= %s AND cal_date BETWEEN %s AND %s AND exchange = ANY(%s)",
                (version, start, end, list(EXCHANGES)),
            ).fetchone()
            assert coverage is not None
            if coverage[0] != len(EXCHANGES) * ((end - start).days + 1):
                raise BatchError(
                    "The selected publication does not cover the requested calendar range"
                )
            missing_bars = []
            if codes:
                present = {
                    row[0]
                    for row in connection.execute(
                        f"SELECT ts_code FROM {STOCK.table} WHERE version_id <= %s AND ts_code = ANY(%s) "
                        f"UNION SELECT ts_code FROM {DAILY.table} WHERE version_id <= %s AND ts_code = ANY(%s)",
                        (version, codes, version, codes),
                    )
                }
                if set(codes) - present:
                    raise BatchError(
                        "Some requested stock codes do not exist in the selected publication"
                    )
                traded = {
                    row[0]
                    for row in connection.execute(
                        f"SELECT DISTINCT ts_code FROM {DAILY.table} WHERE version_id <= %s "
                        "AND trade_date BETWEEN %s AND %s AND ts_code = ANY(%s)",
                        (version, start, end, codes),
                    )
                }
                missing_bars = sorted(present - traded)
            no_reference = connection.execute(
                f"SELECT DISTINCT b.ts_code FROM {DAILY.table} b "
                "WHERE b.version_id <= %s AND b.trade_date BETWEEN %s AND %s "
                "AND (%s::text[] = '{}'::text[] OR b.ts_code = ANY(%s)) "
                f"AND NOT EXISTS (SELECT 1 FROM {STOCK.table} s WHERE s.ts_code = b.ts_code AND s.version_id <= %s) "
                "ORDER BY b.ts_code",
                (version, start, end, codes, codes, version),
            ).fetchall()
            manifest: dict[str, Any] = {
                "publication_version": version,
                "publication_observed_at": observed_at.isoformat(),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "codes": codes,
                "visibility": "historical_source_snapshot_not_strict_pit",
                "coverage": "vendor_cross_sections_not_independently_reconciled",
                "requested_codes_without_bars": missing_bars,
                "codes_without_stock_reference": [row[0] for row in no_reference],
                "files": {},
            }
            for filename, dataset in EXPORTS.items():
                columns = ", ".join(dataset.names)
                query = f"SELECT {columns} FROM {dataset.table} WHERE version_id <= %s"
                params: list[Any] = [version]
                if dataset != STOCK:
                    day = "cal_date" if dataset == CALENDAR else "trade_date"
                    query += f" AND {day} BETWEEN %s AND %s"
                    params.extend((start, end))
                if codes and dataset != CALENDAR:
                    query += " AND ts_code = ANY(%s)"
                    params.append(codes)
                query += " ORDER BY " + ", ".join(dataset.key)
                if dataset == STOCK:
                    # Publish-time stock metadata is a snapshot, not historical sector membership.
                    query = query.replace("SELECT ", "SELECT DISTINCT ON (ts_code) ", 1)
                    query += ", version_id DESC"
                schema = pa.schema(
                    [
                        pa.field(name, ARROW_TYPES[kind.removesuffix(" NOT NULL")])
                        for name, kind in dataset.columns
                    ]
                )
                path = staging / f"{filename}.parquet"
                count = 0
                with (
                    connection.cursor(name="research_rows") as cursor,
                    pq.ParquetWriter(path, schema) as writer,
                ):
                    cursor.execute(query, params)
                    while rows := cursor.fetchmany(20_000):
                        arrays = [
                            pa.array(values, type=field.type)
                            for values, field in zip(zip(*rows), schema, strict=True)
                        ]
                        writer.write_batch(pa.record_batch(arrays, schema=schema))
                        count += len(rows)
                with path.open("rb") as file:
                    digest = hashlib.file_digest(file, "sha256").hexdigest()
                if dataset == DAILY and coverage[1] and not count:
                    raise BatchError(
                        "Open calendar days contain no bars in the selected research scope"
                    )
                manifest["files"][path.name] = {"rows": count, "sha256": digest}
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(destination)
    return manifest
