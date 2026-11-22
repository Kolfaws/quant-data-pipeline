#!/usr/bin/env python3
"""P0-5 写入闸门测试：显式路径、test env fail-fast、2010 边界。

覆盖：
* ``require_market_db_path`` 不再回退相对路径/正式库；
* ``--env test`` 缺 ``MARKET_TEST_DB_PATH`` 立即退出码 2；
* ``end > 2010-12-31`` 对研究库（``MARKET_DB_PATH``）fail-fast，
  ``--allow-post-2010`` 不能解锁研究库；新库需显式 flag；
* ``ingest_market_data.py`` / ``build_tradable_flags.py`` / ``seed_index_demo.py``
  的默认区间为 2010，越界时 CLI 在写库前失败。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import build_tradable_flags
import duckdb
import ingest_market_data
import init_factor_db
import init_market_db
import pytest
import seed_index_demo
from quant_schema.market_ddl import FACTOR_TABLES, WAREHOUSE_TABLES

from data_pipeline import guards
from data_pipeline.db import ConfigError


@pytest.fixture()
def env_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    """把正式库/测试库指向 tmp_path，避免任何真实库被创建或读写。"""
    prod = tmp_path / "prod" / "market.duckdb"
    test = tmp_path / "test" / "market_test.duckdb"
    monkeypatch.setenv("MARKET_DB_PATH", str(prod))
    monkeypatch.setenv("MARKET_TEST_DB_PATH", str(test))
    return prod, test


def _clear_prod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARKET_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)


def _clear_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MARKET_TEST_DB_PATH", raising=False)
    monkeypatch.delenv("DUCKDB_TEST_PATH", raising=False)


def _init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        for table in WAREHOUSE_TABLES + FACTOR_TABLES:
            con.execute(table.ddl())
    finally:
        con.close()


# ---------------------------------------------------------------------------
# require_market_db_path：路径必须显式
# ---------------------------------------------------------------------------
def test_explicit_db_wins_over_env(env_paths, tmp_path: Path) -> None:
    _prod, _test = env_paths
    explicit = tmp_path / "explicit.duckdb"
    assert guards.require_market_db_path(str(explicit)) == explicit
    assert guards.require_market_db_path(str(explicit), env="prod") == explicit


def test_prod_env_requires_market_db_path(monkeypatch, tmp_path: Path) -> None:
    _clear_prod_env(monkeypatch)
    with pytest.raises(ConfigError, match="MARKET_DB_PATH"):
        guards.require_market_db_path(None)


def test_test_env_missing_path_raises_and_never_falls_back(
    monkeypatch, tmp_path: Path
) -> None:
    prod = tmp_path / "prod.duckdb"
    monkeypatch.setenv("MARKET_DB_PATH", str(prod))
    _clear_test_env(monkeypatch)
    with pytest.raises(ConfigError, match="MARKET_TEST_DB_PATH"):
        guards.require_market_db_path(None, env="test")


def test_test_env_rejects_path_equal_to_prod(env_paths, monkeypatch) -> None:
    prod, _test = env_paths
    monkeypatch.setenv("MARKET_TEST_DB_PATH", str(prod))
    with pytest.raises(ConfigError, match="同一文件"):
        guards.require_market_db_path(None, env="test")


def test_unknown_env_raises(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DB_PATH", "x.duckdb")
    with pytest.raises(ConfigError, match="未知环境"):
        guards.require_market_db_path(None, env="staging")


# ---------------------------------------------------------------------------
# 2010 写入闸门
# ---------------------------------------------------------------------------
def test_gate_allows_2010_boundary(env_paths) -> None:
    prod, _test = env_paths
    guards.enforce_research_2010_gate(prod, date(2010, 12, 31))
    guards.enforce_research_2010_gate(prod, "2010-12-31")


def test_gate_rejects_2011_on_research_db_even_with_flag(env_paths) -> None:
    prod, _test = env_paths
    with pytest.raises(ConfigError, match="MARKET_DB_PATH"):
        guards.enforce_research_2010_gate(prod, "2011-01-03", allow_post_2010=True)


def test_gate_requires_flag_for_new_db(env_paths, tmp_path: Path) -> None:
    _prod, test = env_paths
    with pytest.raises(ConfigError, match="allow-post-2010"):
        guards.enforce_research_2010_gate(test, "2011-01-03")
    guards.enforce_research_2010_gate(
        tmp_path / "new_version.duckdb", "2011-01-03", allow_post_2010=True
    )


# ---------------------------------------------------------------------------
# 默认区间
# ---------------------------------------------------------------------------
def test_ingest_defaults_are_2010() -> None:
    args = ingest_market_data.build_parser().parse_args([])
    assert args.start == "2010-01-01"
    assert args.end == "2010-12-31"
    assert args.allow_post_2010 is False
    assert args.db is None


def test_build_flags_default_start_is_2010() -> None:
    args = build_tradable_flags.build_parser().parse_args([])
    assert args.start == "2010-01-01"
    assert args.end is None
    assert args.allow_post_2010 is False


def test_seed_index_defaults_are_2010() -> None:
    args = seed_index_demo.build_parser().parse_args([])
    assert args.start == "2010-01-01"
    assert args.end == "2010-12-31"
    assert args.allow_post_2010 is False
    assert args.db is None


# ---------------------------------------------------------------------------
# CLI fail-fast：越界区间在打开连接/发网络请求前被拒绝
# ---------------------------------------------------------------------------
def test_ingest_cli_rejects_post_2010_before_creating_db(env_paths) -> None:
    prod, _test = env_paths
    rc = ingest_market_data.main(
        ["--db", str(prod), "--start", "2010-01-01", "--end", "2011-01-03"]
    )
    assert rc == 2
    assert not prod.exists()


def test_ingest_cli_flag_cannot_unlock_research_db(env_paths) -> None:
    prod, _test = env_paths
    rc = ingest_market_data.main(
        [
            "--db",
            str(prod),
            "--start",
            "2010-01-01",
            "--end",
            "2011-01-03",
            "--allow-post-2010",
        ]
    )
    assert rc == 2
    assert not prod.exists()


def test_build_flags_cli_rejects_post_2010_before_creating_db(env_paths) -> None:
    prod, _test = env_paths
    rc = build_tradable_flags.main(
        [
            "--db",
            str(prod),
            "--start",
            "2010-01-01",
            "--end",
            "2011-01-03",
            "--apply",
        ]
    )
    assert rc == 2
    assert not prod.exists()


def test_build_flags_allows_post_2010_on_new_db_with_flag(tmp_path: Path) -> None:
    new_db = tmp_path / "new_version.duckdb"
    _init_db(new_db)
    con = duckdb.connect(str(new_db))
    try:
        con.execute(
            "INSERT INTO fact_daily (ts_code, trade_date, close, vol) "
            "VALUES ('A', DATE '2011-01-04', 10, 100)"
        )
        con.execute(
            "INSERT INTO fact_stk_limit (ts_code, trade_date, up_limit, down_limit) "
            "VALUES ('A', DATE '2011-01-04', 11, 9)"
        )
        con.execute(
            "INSERT INTO dim_stock_basic (ts_code, list_status, list_date) "
            "VALUES ('A', 'L', DATE '2011-01-01')"
        )
    finally:
        con.close()

    rc = build_tradable_flags.main(
        [
            "--db",
            str(new_db),
            "--start",
            "2011-01-04",
            "--end",
            "2011-01-04",
            "--apply",
            "--allow-post-2010",
        ]
    )
    assert rc == 0
    con = duckdb.connect(str(new_db), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM fact_tradable_flag").fetchone()[0] == 1
    finally:
        con.close()


def test_seed_index_cli_rejects_post_2010_before_network(env_paths) -> None:
    prod, _test = env_paths
    rc = seed_index_demo.main(
        ["--db", str(prod), "--start", "2010-01-01", "--end", "2011-01-03"]
    )
    assert rc == 2
    assert not prod.exists()


# ---------------------------------------------------------------------------
# init_market_db / init_factor_db: --env test 缺路径 fail-fast
# ---------------------------------------------------------------------------
def test_init_market_db_test_env_missing_path_returns_2(
    monkeypatch, tmp_path: Path
) -> None:
    prod = tmp_path / "prod.duckdb"
    monkeypatch.setenv("MARKET_DB_PATH", str(prod))
    _clear_test_env(monkeypatch)
    assert init_market_db.main(["init", "--env", "test"]) == 2
    # 绝不回退正式库：正式库文件没有被创建
    assert not prod.exists()


def test_init_factor_db_test_env_missing_path_returns_2(
    monkeypatch, tmp_path: Path
) -> None:
    prod = tmp_path / "prod.duckdb"
    monkeypatch.setenv("MARKET_DB_PATH", str(prod))
    _clear_test_env(monkeypatch)
    assert init_factor_db.main(["init", "--env", "test"]) == 2
    assert not prod.exists()


def test_init_market_db_default_requires_explicit_path(monkeypatch) -> None:
    _clear_prod_env(monkeypatch)
    assert init_market_db.main(["init"]) == 2


def test_init_factor_db_default_requires_explicit_path(monkeypatch) -> None:
    _clear_prod_env(monkeypatch)
    assert init_factor_db.main(["init"]) == 2


def test_init_market_db_test_env_uses_test_path(env_paths) -> None:
    prod, test = env_paths
    assert init_market_db.main(["init", "--env", "test"]) == 0
    assert test.is_file()
    assert not prod.exists()


def test_config_error_message_does_not_leak_path(env_paths) -> None:
    prod, _test = env_paths
    with pytest.raises(ConfigError) as excinfo:
        guards.enforce_research_2010_gate(prod, "2011-01-03")
    assert str(prod) not in str(excinfo.value)
