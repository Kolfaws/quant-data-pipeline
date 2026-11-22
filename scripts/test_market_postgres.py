"""Contract and isolated PostgreSQL integration tests for the publication path."""

# ruff: noqa: E402 -- The optional PostgreSQL driver must be checked before importing its consumers.

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import duckdb
import polars as pl
import pytest

psycopg = pytest.importorskip("psycopg")

from data_pipeline.postgres_connection import postgres_environment
from data_pipeline.postgres_market import (
    BatchError,
    collect_market,
    init_postgres,
    publish_market,
)
from data_pipeline.postgres_nav import init_nav, publish_nav, read_nav
from data_pipeline.postgres_research import export_research
from data_pipeline.sources.tushare_src import TushareSource
from quant_schema.backtest_ddl import BACKTEST_TABLES
from quant_schema.postgres_ddl import ADJUSTMENT, DAILY, PUBLICATION, STOCK

DAY = date(2010, 1, 4)


def test_postgres_uses_explicit_env_before_shared_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in ("POSTGRE_DB", "POSTGRE_IP", "QUANTDATA_POSTGRES_ENV"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / "shared.env").write_text(
        "POSTGRE_DB=shared\nPOSTGRE_IP=localhost:5432\n", encoding="utf-8"
    )
    selected = tmp_path / "selected.env"
    selected.write_text(
        "QUANTDATA_POSTGRES_ENV=shared.env\nPOSTGRE_DB=selected\n", encoding="utf-8"
    )
    settings = postgres_environment(selected)
    assert settings["POSTGRE_DB"] == "selected"
    assert settings["POSTGRE_IP"] == "localhost:5432"
    assert "POSTGRE_DB" not in os.environ
    monkeypatch.setenv("POSTGRE_DB", "process")
    assert postgres_environment(selected)["POSTGRE_DB"] == "process"


class FixtureSource(TushareSource):
    def fetch_trade_cal(
        self, start: str, end: str, exchange: str = "SSE"
    ) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "exchange": [exchange],
                "cal_date": [DAY],
                "is_open": [True],
                "pretrade_date": [DAY - timedelta(days=4)],
            }
        )

    def fetch_stock_snapshot(self, exchange: str, status: str) -> pl.DataFrame:
        if status == "P":
            return pl.DataFrame()
        suffix = "SH" if exchange == "SSE" else "SZ"
        return pl.DataFrame(
            {
                "ts_code": [f"00000{1 if status == 'L' else 2}.{suffix}"],
                "symbol": [None],
                "name": ["sample"],
                "area": [None],
                "industry": [None],
                "market": [None],
                "exchange": [exchange],
                "list_status": [status],
                "list_date": [date(2000, 1, 1)],
                "delist_date": [date(2009, 1, 1) if status == "D" else None],
                "is_hs": [None],
            }
        )

    def fetch_daily_cross_section(self, day: str) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "ts_code": ["000001.SH", "000001.SZ"],
                "trade_date": [DAY, DAY],
                "open": [10.0, 11.0],
                "high": [11.0, 12.0],
                "low": [9.0, 10.0],
                "close": [10.0, 11.0],
                "pre_close": [10.0, 11.0],
                "chg": [0.0, 0.0],
                "pct_chg": [0.0, 0.0],
                "vol": [350.0, 400.0],
                "amount": [91.1234, 1e9],
            }
        )

    def fetch_adjustment_cross_section(self, day: str) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "ts_code": ["000001.SH", "000001.SZ", "000002.SH"],
                "trade_date": [DAY, DAY, DAY],
                "adj_factor": [1.0, 1.5, 1.0],
            }
        )


def test_missing_adjustment_fails_before_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = FixtureSource()
    response = source.fetch_adjustment_cross_section("20100104").head(1)
    monkeypatch.setattr(source, "fetch_adjustment_cross_section", lambda _: response)
    with pytest.raises(BatchError, match="no adjustment factor"):
        collect_market(source, DAY, DAY)


def test_publish_retry_conflict_and_duckdb_snapshot(tmp_path: Path) -> None:
    dsn = os.getenv("TEST_QUANTDATA_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set TEST_QUANTDATA_POSTGRES_DSN to a fresh isolated database")
    with psycopg.connect(dsn, autocommit=True) as database:
        assert database.execute(f"SELECT to_regclass('{PUBLICATION}')").fetchone() == (
            None,
        )
        with database.transaction(force_rollback=True):
            database.execute("CREATE SCHEMA market")
            database.execute("CREATE TABLE market.stock_daily (id int)")
            with pytest.raises(BatchError, match="Unversioned"):
                init_postgres(database)
        init_postgres(database)
        init_postgres(database)
        batch = collect_market(FixtureSource(), DAY, DAY)
        publication, counts = publish_market(database, batch)
        assert counts[DAILY.table] == counts[ADJUSTMENT.table] == 2
        assert counts[STOCK.table] == 4
        assert publish_market(database, batch) == (
            publication,
            dict.fromkeys(counts, 0),
        )
        renamed = batch.frames[STOCK].with_columns(pl.lit("new name").alias("name"))
        changed = batch.frames[DAILY].with_columns(
            (pl.col("close") + 0.1).alias("close")
        )
        with pytest.raises(BatchError, match="Historical change"):
            publish_market(
                database,
                replace(batch, frames={**batch.frames, DAILY: changed, STOCK: renamed}),
            )
        assert database.execute(f"SELECT count(*) FROM {PUBLICATION}").fetchone() == (
            1,
        )
        assert database.execute(f"SELECT count(*) FROM {STOCK.table}").fetchone() == (
            4,
        )
        later, _ = publish_market(
            database, replace(batch, frames={**batch.frames, STOCK: renamed})
        )
        assert later > publication
        assert publish_market(database, batch) == (
            publication,
            dict.fromkeys(counts, 0),
        )
        newer_observation = replace(
            batch,
            observed_at=batch.observed_at + timedelta(seconds=1),
            frames={**batch.frames, STOCK: renamed},
        )
        assert publish_market(database, newer_observation) == (
            later,
            dict.fromkeys(counts, 0),
        )
        assert database.execute(f"SELECT count(*) FROM {PUBLICATION}").fetchone() == (
            2,
        )
        output = tmp_path / "snapshot"
        with pytest.raises(BatchError, match="calendar range"):
            export_research(
                database, output, start=DAY, end=DAY + timedelta(days=1), codes=[]
            )
        assert not output.exists()
        manifest = export_research(
            database,
            output,
            start=DAY,
            end=DAY,
            codes=["000001.SH"],
            version=publication,
        )
        assert manifest["files"]["fact_daily.parquet"]["rows"] == 1
        with duckdb.connect() as research:
            assert research.execute(
                "SELECT name FROM read_parquet(?)",
                [str(output / "dim_stock_basic.parquet")],
            ).fetchone() == ("sample",)
            assert research.execute(
                "SELECT close FROM read_parquet(?)",
                [str(output / "fact_daily.parquet")],
            ).fetchone() == (10.0,)

        nav_file = tmp_path / "backtest.duckdb"
        second = DAY + timedelta(days=1)
        with duckdb.connect(str(nav_file)) as backtest:
            for table in BACKTEST_TABLES:
                backtest.execute(table.ddl())
            backtest.execute(
                "INSERT INTO bt_runs (run_id, strategy_id, status, start_date, end_date) "
                "VALUES ('fixture', 'buy-hold', 'success', ?, ?)",
                (DAY, second),
            )
            backtest.executemany(
                "INSERT INTO bt_nav (run_id, trade_date, nav, ret_1d, cum_ret, drawdown) "
                "VALUES ('fixture', ?, ?, ?, ?, ?)",
                ((DAY, 1.0, 0.0, 0.0, 0.0), (second, 1.1, 0.1, 0.1, 0.0)),
            )
        init_nav(database)
        init_nav(database)
        with pytest.raises(BatchError, match="version does not exist"):
            publish_nav(database, nav_file, "fixture", 999_999)
        with pytest.raises(BatchError, match="cover the NAV calendar range"):
            publish_nav(database, nav_file, "fixture", publication)
        with duckdb.connect(str(nav_file)) as backtest:
            backtest.execute("DELETE FROM bt_nav WHERE trade_date = ?", (second,))
            backtest.execute("UPDATE bt_runs SET end_date = ?", (DAY,))
        assert publish_nav(database, nav_file, "fixture", publication) == (1, 1, True)
        assert publish_nav(database, nav_file, "fixture", publication) == (1, 1, False)
        with duckdb.connect(str(nav_file)) as backtest:
            backtest.execute("UPDATE bt_runs SET strategy_name='new version'")
        assert publish_nav(database, nav_file, "fixture", publication) == (2, 1, True)
        assert read_nav(database, "fixture", 1) == (
            publication,
            [(DAY, 1.0, 0.0, 0.0, 0.0)],
        )
        assert read_nav(database, "fixture", 2) == read_nav(database, "fixture", 1)
