#!/usr/bin/env python3
"""init_factor_db.py 的 pytest 用例。

运行：
    pytest -q test_init_factor_db.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import init_factor_db as factor
import init_market_db as market
import pytest


def _table_names(con) -> set[str]:
    rows = con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _view_names(con) -> set[str]:
    rows = con.execute(
        "SELECT view_name FROM duckdb_views() WHERE schema_name = 'main'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _column_names(con, name: str) -> list[str]:
    rows = con.execute(f'DESCRIBE "{name}"').fetchall()
    return [str(row[0]) for row in rows]


@pytest.fixture()
def market_db(tmp_path: Path) -> Path:
    db = tmp_path / "market.duckdb"
    with market.database(db) as con:
        market.init_schema(con)
    return db


@pytest.fixture()
def factor_db(market_db: Path) -> Path:
    with factor.database(market_db) as con:
        factor.init_schema(con)
    return market_db


# ---------------------------------------------------------------------------
# 正常路径 / 建表建视图
# ---------------------------------------------------------------------------
def test_init_creates_factor_tables_and_views(market_db: Path) -> None:
    with factor.database(market_db) as con:
        factor.init_schema(con)
        tables = _table_names(con)
        views = _view_names(con)

    assert {t.name for t in factor.TABLES} <= tables
    assert set(factor.VIEW_NAMES) <= views


def test_init_is_idempotent_and_versions_isolated(market_db: Path) -> None:
    for _ in range(3):
        with factor.database(market_db) as con:
            factor.init_schema(con)

    with factor.database(market_db, read_only=True) as con:
        assert factor.installed_version(con) == factor.SCHEMA_VERSION
        assert factor.installed_version(con, "warehouse") == market.SCHEMA_VERSION
        assert (
            factor._scalar(
                con,
                "SELECT count(*) FROM meta_schema_version WHERE component = 'factor'",
            )
            == 1
        )
        assert (
            factor._scalar(
                con,
                "SELECT count(*) FROM meta_schema_version "
                "WHERE component = 'warehouse'",
            )
            == 1
        )


def test_shared_tables_use_exact_market_definitions() -> None:
    for name in ("meta_schema_version", "meta_ingest_log"):
        ft = next(t for t in factor.TABLES if t.name == name)
        mt = next(t for t in market.TABLES if t.name == name)
        assert ft.columns == mt.columns
        assert ft.constraints == mt.constraints


def test_market_init_after_factor_keeps_both_versions(market_db: Path) -> None:
    with factor.database(market_db) as con:
        factor.init_schema(con)
        market.init_schema(con)
        assert market.installed_version(con) == market.SCHEMA_VERSION
        assert factor.installed_version(con) == factor.SCHEMA_VERSION
        assert factor.installed_version(con, "warehouse") == market.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 依赖 / 版本
# ---------------------------------------------------------------------------
def test_init_requires_warehouse(tmp_path: Path) -> None:
    db = tmp_path / "empty.duckdb"
    with (
        factor.database(db) as con,
        pytest.raises(factor.SchemaError, match="warehouse"),
    ):
        factor.init_schema(con)


def test_warehouse_version_too_old(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        con.execute(
            "UPDATE meta_schema_version SET version = '1.0.0' "
            "WHERE component = 'warehouse'"
        )
        with pytest.raises(factor.SchemaError, match="1.1.0"):
            factor.verify_schema(con, verify_views=False)


def test_component_validation(factor_db: Path) -> None:
    with factor.database(factor_db) as con, pytest.raises(factor.ConfigError):
        factor.installed_version(con, "Bad-Name")


# ---------------------------------------------------------------------------
# 结构漂移
# ---------------------------------------------------------------------------
def test_verify_detects_missing_factor_table(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        con.execute("DROP VIEW IF EXISTS v_factor_wide")
        con.execute("DROP VIEW IF EXISTS v_factor_valid")
        con.execute("DROP TABLE fact_factor_daily")
        with pytest.raises(factor.SchemaError, match="缺表 fact_factor_daily"):
            factor.verify_schema(con)


def test_verify_detects_extra_column(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        con.execute("ALTER TABLE fact_factor_daily ADD COLUMN junk DOUBLE")
        with pytest.raises(factor.SchemaError, match="多余列"):
            factor.verify_schema(con, verify_views=False)


def test_verify_detects_type_drift(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        con.execute("DROP VIEW IF EXISTS v_factor_wide")
        con.execute("DROP VIEW IF EXISTS v_factor_valid")
        con.execute("DROP TABLE fact_factor_daily")
        con.execute("""
            CREATE TABLE fact_factor_daily (
                ts_code VARCHAR NOT NULL,
                trade_date DATE NOT NULL,
                factor_id INTEGER NOT NULL,
                value VARCHAR,
                is_stale BOOLEAN NOT NULL DEFAULT FALSE,
                source_batch_id BIGINT
            )
            """)
        with pytest.raises(
            factor.SchemaError,
            match=r"fact_factor_daily\.value 类型",
        ):
            factor.verify_schema(con, verify_views=False)


def test_verify_detects_missing_view(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        con.execute("DROP VIEW v_factor_valid")
        with pytest.raises(factor.SchemaError, match="缺视图"):
            factor.verify_schema(con)


# ---------------------------------------------------------------------------
# 幂等重建 / 视图
# ---------------------------------------------------------------------------
def test_range_rebuild_is_idempotent(factor_db: Path) -> None:
    rows = [
        ("000001.SZ", date(2024, 1, 2), 1, 0.1, False, None),
        ("000001.SZ", date(2024, 1, 3), 1, 0.2, False, None),
    ]
    with factor.database(factor_db) as con:
        con.execute(
            "INSERT INTO meta_factor_registry "
            "(factor_id, factor_name, value_type) "
            "VALUES (1, 'mom_20d', 'raw')"
        )
        con.executemany(
            "INSERT INTO fact_factor_daily "
            "(ts_code, trade_date, factor_id, value, is_stale, source_batch_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        before = factor._scalar(con, "SELECT count(*) FROM fact_factor_daily")

        con.execute(
            "DELETE FROM fact_factor_daily "
            "WHERE factor_id = 1 "
            "AND trade_date BETWEEN DATE '2024-01-01' AND DATE '2024-01-31'"
        )
        con.executemany(
            "INSERT INTO fact_factor_daily "
            "(ts_code, trade_date, factor_id, value, is_stale, source_batch_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        after = factor._scalar(con, "SELECT count(*) FROM fact_factor_daily")

    assert before == after == 2


def test_tradable_flag_filters_valid_view(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        con.execute(
            "INSERT INTO meta_factor_registry "
            "(factor_id, factor_name, value_type) "
            "VALUES (1, 'mom_20d', 'raw')"
        )
        con.executemany(
            "INSERT INTO fact_factor_daily "
            "(ts_code, trade_date, factor_id, value, is_stale) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("000001.SZ", date(2024, 1, 2), 1, 0.1, False),
                ("000001.SZ", date(2024, 1, 3), 1, 0.2, False),
            ],
        )
        con.executemany(
            "INSERT INTO fact_tradable_flag "
            "(ts_code, trade_date, is_suspended, is_st, is_limit_up, "
            " is_limit_down, is_buyable, is_sellable, in_universe) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "000001.SZ",
                    date(2024, 1, 2),
                    False,
                    False,
                    False,
                    False,
                    True,
                    True,
                    True,
                ),
                (
                    "000001.SZ",
                    date(2024, 1, 3),
                    False,
                    False,
                    True,
                    False,
                    False,
                    False,
                    True,
                ),
            ],
        )
        got = con.execute(
            "SELECT ts_code, trade_date, factor_id, value "
            "FROM v_factor_valid ORDER BY trade_date"
        ).fetchall()

    assert len(got) == 1
    assert got[0][0] == "000001.SZ"
    assert got[0][1] == date(2024, 1, 2)


def test_wide_view_empty_registry_has_two_columns(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        assert _column_names(con, "v_factor_wide") == [
            "ts_code",
            "trade_date",
        ]


def test_wide_view_refresh_reflects_active_factors(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        assert len(_column_names(con, "v_factor_wide")) == 2

        con.execute(
            "INSERT INTO meta_factor_registry "
            "(factor_id, factor_name, value_type, is_active) VALUES "
            "(1, 'mom_20d', 'raw', TRUE), "
            "(2, 'value_ep', 'raw', FALSE)"
        )
        con.executemany(
            "INSERT INTO fact_factor_daily "
            "(ts_code, trade_date, factor_id, value, is_stale) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("000001.SZ", date(2024, 1, 2), 1, 0.1, False),
                ("000001.SZ", date(2024, 1, 2), 2, 999.0, False),
            ],
        )

        factor.refresh_views(con)
        cols = _column_names(con, "v_factor_wide")
        row = con.execute("SELECT * FROM v_factor_wide").fetchone()

    assert len(cols) == 3
    assert row is not None
    assert row[0] == "000001.SZ"
    assert row[1] == date(2024, 1, 2)
    assert row[2] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# 统计 / 资源 / CLI
# ---------------------------------------------------------------------------
def test_table_row_counts(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        counts = factor.table_row_counts(con)

    assert set(counts) == {t.name for t in factor.TABLES}
    assert counts["meta_schema_version"] == 2
    assert counts["fact_factor_daily"] == 0
    assert counts["fact_tradable_flag"] == 0


def test_read_only_readers_coexist(factor_db: Path) -> None:
    with (
        factor.database(factor_db, read_only=True) as a,
        factor.database(factor_db, read_only=True) as b,
    ):
        assert factor.installed_version(a) == factor.SCHEMA_VERSION
        assert factor.installed_version(b) == factor.SCHEMA_VERSION


def test_same_process_rw_connections_share_instance(factor_db: Path) -> None:
    with factor.database(factor_db), factor.database(factor_db) as con2:
        assert factor.installed_version(con2) == factor.SCHEMA_VERSION


def test_bulk_insert_10k_rows(factor_db: Path) -> None:
    rows = [
        ("000001.SZ", date(2024, 1, 2) + timedelta(days=i), 1, float(i), False, None)
        for i in range(10_000)
    ]
    with factor.database(factor_db) as con:
        con.execute(
            "INSERT INTO meta_factor_registry "
            "(factor_id, factor_name, value_type) "
            "VALUES (1, 'mom_20d', 'raw')"
        )
        con.executemany(
            "INSERT INTO fact_factor_daily "
            "(ts_code, trade_date, factor_id, value, is_stale, source_batch_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        count = factor._scalar(con, "SELECT count(*) FROM fact_factor_daily")
    assert count == 10_000


def test_quality_table_default_computed_at(factor_db: Path) -> None:
    with factor.database(factor_db) as con:
        con.execute(
            "INSERT INTO fact_factor_quality "
            "(factor_id, trade_date, n_total, n_valid, n_stale, n_outlier, coverage) "
            "VALUES (1, DATE '2024-01-02', 100, 90, 0, 1, 0.9)"
        )
        computed_at = factor._scalar(con, "SELECT computed_at FROM fact_factor_quality")
    assert computed_at is not None


def test_cli_exit_codes(tmp_path: Path, market_db: Path) -> None:
    assert factor.main(["init", "--db", str(market_db)]) == 0
    assert factor.main(["check", "--db", str(market_db)]) == 0
    assert (
        factor.main(
            [
                "init",
                "--db",
                str(market_db),
                "--memory-limit",
                "4G",
            ]
        )
        == 2
    )

    empty = tmp_path / "empty.duckdb"
    assert factor.main(["check", "--db", str(empty)]) == 1
