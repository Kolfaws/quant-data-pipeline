"""Publish completed DuckDB runs and read versioned NAV from PostgreSQL."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from math import isclose, isfinite
from pathlib import Path
from typing import Any

import duckdb
from psycopg import Connection
from quant_schema.constants import BT_NAV, BT_RUNS
from quant_schema.postgres_backtest_ddl import (
    BACKTEST_NAV,
    BACKTEST_RUN,
    NAV_COMPONENT,
    POSTGRES_BACKTEST_DDL,
    POSTGRES_NAV_VERSION,
)
from quant_schema.postgres_ddl import CALENDAR, PUBLICATION

from data_pipeline.postgres_market import EXCHANGES, BatchError, check_version

NAV_LOCK = 811402986858541053
NAV_COLUMNS = ("trade_date", "nav", "ret_1d", "cum_ret", "drawdown")
NavRow = tuple[date, float, float, float, float]


def init_nav(connection: Connection[Any]) -> None:
    with connection.transaction():
        check_version(connection)
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (NAV_LOCK,))
        version = _nav_version(connection)
        exists = connection.execute(
            "SELECT to_regclass(%s) IS NOT NULL, to_regclass(%s) IS NOT NULL",
            (BACKTEST_RUN, BACKTEST_NAV),
        ).fetchone()
        if version == (POSTGRES_NAV_VERSION,) and exists == (True, True):
            return
        if version is not None or exists != (False, False):
            raise BatchError(
                "Backtest NAV schema needs inspection or an explicit migration"
            )
        for statement in POSTGRES_BACKTEST_DDL:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO control.schema_version VALUES (%s, %s)",
            (NAV_COMPONENT, POSTGRES_NAV_VERSION),
        )


def _nav_version(connection: Connection[Any]) -> tuple[str] | None:
    return connection.execute(
        "SELECT version FROM control.schema_version WHERE component = %s",
        (NAV_COMPONENT,),
    ).fetchone()


def _load_run(path: Path, run_id: str) -> tuple[tuple[Any, ...], list[NavRow]]:
    with duckdb.connect(str(path), read_only=True) as source:
        source.begin()
        run = source.execute(
            f"SELECT strategy_id, strategy_name, benchmark_id, engine_version, config_hash, start_date, end_date "
            f"FROM {BT_RUNS} WHERE run_id = ? AND status = 'success'",
            (run_id,),
        ).fetchone()
        if run is None:
            raise BatchError("The selected DuckDB run is missing or did not succeed")
        rows = source.execute(
            f"SELECT {', '.join(NAV_COLUMNS)} FROM {BT_NAV} WHERE run_id = ? ORDER BY trade_date",
            (run_id,),
        ).fetchall()
        inconsistent_benchmark = source.execute(
            f"SELECT 1 FROM {BT_NAV} WHERE run_id = ? AND benchmark_id IS DISTINCT FROM ? LIMIT 1",
            (run_id, run[2]),
        ).fetchone()
        if inconsistent_benchmark is not None:
            raise BatchError("Run and daily NAV benchmark metadata differ")
    if not rows or (rows[0][0], rows[-1][0]) != tuple(run[-2:]):
        raise BatchError("NAV dates do not match the completed run")
    previous, peak = 1.0, 1.0
    for index, (day, nav, ret, cumulative, drawdown) in enumerate(rows):
        if index and day <= rows[index - 1][0]:
            raise BatchError("NAV dates must be unique and increasing")
        if (
            not all(
                value is not None and isfinite(value)
                for value in (nav, ret, cumulative, drawdown)
            )
            or nav <= 0
        ):
            raise BatchError("NAV rows contain missing, nonfinite or invalid values")
        peak = max(peak, nav)
        if (
            (index == 0 and (nav != 1.0 or ret != 0.0))
            or not isclose(nav, previous * (1 + ret), rel_tol=1e-9, abs_tol=1e-12)
            or not isclose(cumulative, nav - 1, abs_tol=1e-10)
            or not isclose(drawdown, nav / peak - 1, abs_tol=1e-10)
        ):
            raise BatchError("NAV, daily return or drawdown is inconsistent")
        previous = nav
    return run, rows


def _validate_input_version(
    connection: Connection[Any], version: int, rows: list[NavRow]
) -> None:
    if (
        connection.execute(
            f"SELECT 1 FROM {PUBLICATION} WHERE version_id = %s", (version,)
        ).fetchone()
        is None
    ):
        raise BatchError("The selected market publication version does not exist")
    start, end = rows[0][0], rows[-1][0]
    calendar = connection.execute(
        f"SELECT cal_date, is_open FROM {CALENDAR.table} WHERE version_id <= %s "
        "AND cal_date BETWEEN %s AND %s AND exchange = ANY(%s)",
        (version, start, end, list(EXCHANGES)),
    ).fetchall()
    if len(calendar) != ((end - start).days + 1) * len(EXCHANGES):
        raise BatchError("Market version does not cover the NAV calendar range")
    open_days = {day for day, is_open in calendar if is_open}
    if any(row[0] not in open_days for row in rows):
        raise BatchError("NAV includes a nontrading day in the selected market version")


def publish_nav(
    connection: Connection[Any],
    path: Path,
    run_id: str,
    input_version: int,
) -> tuple[int, int, bool]:
    run, rows = _load_run(path, run_id)
    digest = hashlib.sha256(
        json.dumps([run, rows], default=str, allow_nan=False).encode()
    ).hexdigest()
    with connection.transaction():
        if _nav_version(connection) != (POSTGRES_NAV_VERSION,):
            raise BatchError("Run init-nav before publishing NAV")
        _validate_input_version(connection, input_version, rows)
        connection.execute("SELECT pg_advisory_xact_lock(%s)", (NAV_LOCK,))
        prior = connection.execute(
            f"SELECT revision FROM {BACKTEST_RUN} WHERE run_id = %s AND input_version = %s AND content_sha256 = %s",
            (run_id, input_version, digest),
        ).fetchone()
        if prior is not None:
            return prior[0], len(rows), False
        inserted = connection.execute(
            f"INSERT INTO {BACKTEST_RUN} (run_id, revision, input_version, strategy_id, strategy_name, "
            "benchmark_id, engine_version, config_hash, start_date, end_date, rows, content_sha256) "
            f"VALUES (%s, (SELECT coalesce(max(revision), 0) + 1 FROM {BACKTEST_RUN} WHERE run_id = %s), "
            "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING revision",
            (run_id, run_id, input_version, *run, len(rows), digest),
        ).fetchone()
        assert inserted is not None
        revision = inserted[0]
        with (
            connection.cursor() as cursor,
            cursor.copy(
                f"COPY {BACKTEST_NAV} (run_id, revision, {', '.join(NAV_COLUMNS)}) FROM STDIN"
            ) as copy,
        ):
            for row in rows:
                copy.write_row((run_id, revision, *row))
    return revision, len(rows), True


def read_nav(
    connection: Connection[Any],
    run_id: str,
    revision: int,
) -> tuple[int, list[NavRow]]:
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        header = connection.execute(
            f"SELECT input_version, rows FROM {BACKTEST_RUN} WHERE run_id = %s AND revision = %s",
            (run_id, revision),
        ).fetchone()
        if header is None:
            raise BatchError("The requested backtest NAV revision does not exist")
        rows = connection.execute(
            f"SELECT {', '.join(NAV_COLUMNS)} FROM {BACKTEST_NAV} "
            "WHERE run_id = %s AND revision = %s ORDER BY trade_date",
            (run_id, revision),
        ).fetchall()
        if len(rows) != header[1]:
            raise BatchError("Stored NAV count does not match the run metadata")
    return header[0], rows
