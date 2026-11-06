#!/usr/bin/env python3
"""init_market_db.py 的 pytest 用例  运行：pytest -q test_init_market_db.py"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Final

import duckdb
import init_market_db as mod
import pytest

POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="POSIX 文件权限语义")


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------
_SIZE_RE: Final = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KMGT]?i?B)\s*$", re.IGNORECASE)
_SIZE_MULT: Final[dict[str, int]] = {
    "B": 1,
    "KB": 1024,
    "KIB": 1024,
    "MB": 1024**2,
    "MIB": 1024**2,
    "GB": 1024**3,
    "GIB": 1024**3,
    "TB": 1024**4,
    "TIB": 1024**4,
}


def _size_to_bytes(text: str) -> float:
    """把 '4GB' / '976.6 MiB' 解析成字节数  只用于比较量级，不苛求单位口径一致"""
    match = _SIZE_RE.match(text.strip())
    if match is None:
        raise AssertionError(f"无法解析容量字符串：{text!r}")
    return float(match.group(1)) * _SIZE_MULT[match.group(2).upper()]


def _table_names(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main'"
    ).fetchall()
    return {str(r[0]) for r in rows}


def _view_names(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT view_name FROM duckdb_views() WHERE schema_name = 'main'"
    ).fetchall()
    return {str(r[0]) for r in rows}


# ---------------------------------------------------------------------------
# 建表 / 视图
# ---------------------------------------------------------------------------
def test_init_creates_tables_and_views(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        mod.init_schema(con)
        tables = _table_names(con)
        views = _view_names(con)

    expected_tables = {t.name for t in mod.TABLES}
    assert expected_tables <= tables, f"缺表：{expected_tables - tables}"
    assert set(mod.VIEWS) <= views, f"缺视图：{set(mod.VIEWS) - views}"


def test_init_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "m.duckdb"
    for _ in range(3):
        with mod.database(db) as con:
            mod.init_schema(con)

    with mod.database(db, read_only=True) as con:
        expected = {t.name for t in mod.TABLES}
        actual = _table_names(con)

        # 1) 该有的都在
        assert expected <= actual, f"缺表：{expected - actual}"
        # 2) 没有同前缀的漂移表（不依赖 duckdb_tables().internal，跨版本安全）
        drifted = {
            n for n in actual - expected if n.startswith(("meta_", "dim_", "fact_"))
        }
        assert not drifted, f"出现非预期表：{drifted}"
        # 3) 版本号单行、值正确
        assert mod.installed_version(con) == mod.SCHEMA_VERSION


def test_init_does_not_duplicate_version_rows(tmp_path: Path) -> None:
    """ON CONFLICT 若被删掉，三连 init 会产生 3 行，用 row_count 钉死"""
    db = tmp_path / "m.duckdb"
    for _ in range(3):
        with mod.database(db) as con:
            mod.init_schema(con)
    with mod.database(db, read_only=True) as con:
        rows = mod._scalar(
            con,
            "SELECT count(*) FROM meta_schema_version WHERE component = 'warehouse'",
        )
    assert rows == 1


# ---------------------------------------------------------------------------
# 结构漂移
# ---------------------------------------------------------------------------
def test_verify_detects_schema_drift(tmp_path: Path) -> None:
    db = tmp_path / "m.duckdb"
    raw = duckdb.connect(str(db))
    try:
        raw.execute("CREATE TABLE fact_daily (ts_code VARCHAR, trade_date DATE)")
        with pytest.raises(mod.SchemaError, match="fact_daily"):
            mod.init_schema(raw)
    finally:
        raw.close()


def test_verify_detects_extra_column(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        mod.init_schema(con)
        con.execute("ALTER TABLE fact_daily ADD COLUMN junk DOUBLE")
        with pytest.raises(mod.SchemaError, match="多余列"):
            mod.verify_schema(con)


# ---------------------------------------------------------------------------
# memory_limit
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["4GB", "512MB", "1.5GB", "2TB", "8gb"])
def test_memory_limit_accepts_valid(value: str) -> None:
    with mod.database(":memory:", memory_limit=value) as con:
        echoed = str(mod._scalar(con, "SELECT current_setting('memory_limit')"))
    assert echoed.strip(), f"memory_limit 未被接受：{value!r}"
    assert _size_to_bytes(echoed) > 0


def test_memory_limit_takes_effect() -> None:
    """不只是「不报错」，要证明配置真的落到 buffer manager 上"""
    with mod.database(":memory:", memory_limit="256MB") as con:
        small = _size_to_bytes(
            str(mod._scalar(con, "SELECT current_setting('memory_limit')"))
        )
    with mod.database(":memory:", memory_limit="512MB") as con:
        large = _size_to_bytes(
            str(mod._scalar(con, "SELECT current_setting('memory_limit')"))
        )
    assert 0 < small < large, (small, large)


@pytest.mark.parametrize("value", ["4G", "GB", "4 GB", "-1GB", "4GB; DROP TABLE x", ""])
def test_memory_limit_rejects_invalid(value: str) -> None:
    with pytest.raises(mod.ConfigError):
        mod.connect(":memory:", memory_limit=value)


# ---------------------------------------------------------------------------
# threads
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("threads", [0, -1, 129])
def test_threads_out_of_range(threads: int) -> None:
    with pytest.raises(mod.ConfigError):
        mod.connect(":memory:", threads=threads)


def test_threads_rejects_bool() -> None:
    with pytest.raises(mod.ConfigError):
        mod.connect(":memory:", threads=True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 文件权限
# ---------------------------------------------------------------------------
@POSIX_ONLY
def test_file_permissions(tmp_path: Path) -> None:
    db = tmp_path / "sub" / "m.duckdb"
    with mod.database(db) as con:
        mod.init_schema(con)

    assert db.is_file()
    assert stat.S_IMODE(db.stat().st_mode) == 0o600, oct(
        stat.S_IMODE(db.stat().st_mode)
    )
    assert stat.S_IMODE(db.parent.stat().st_mode) == 0o700, oct(
        stat.S_IMODE(db.parent.stat().st_mode)
    )


@POSIX_ONLY
def test_permissions_restored_on_reconnect(tmp_path: Path) -> None:
    """库文件被外部改松后，重连必须重新收紧到 0600"""
    db = tmp_path / "m.duckdb"
    with mod.database(db) as con:
        mod.init_schema(con)

    db.chmod(0o644)
    assert stat.S_IMODE(db.stat().st_mode) == 0o644

    with mod.database(db):
        pass
    assert stat.S_IMODE(db.stat().st_mode) == 0o600


# ---------------------------------------------------------------------------
# temp_dir 与单引号转义
# ---------------------------------------------------------------------------
def test_temp_dir_created_and_escaped(tmp_path: Path) -> None:
    tmp = tmp_path / "duck tmp's"  # 单引号：不转义会让 SET 语句语法错误
    with mod.database(":memory:", temp_dir=tmp) as con:
        echoed = str(mod._scalar(con, "SELECT current_setting('temp_directory')"))

    assert echoed.strip(), "temp_directory 未被接受"
    assert Path(echoed).resolve() == tmp.resolve(), (echoed, str(tmp))
    assert tmp.is_dir()


@POSIX_ONLY
def test_temp_dir_permissions(tmp_path: Path) -> None:
    tmp = tmp_path / "spill"
    with mod.database(":memory:", temp_dir=tmp):
        pass
    assert stat.S_IMODE(tmp.stat().st_mode) & 0o077 == 0


# ---------------------------------------------------------------------------
# 只读 / 单写者
# ---------------------------------------------------------------------------
def test_read_only_connection_can_query(tmp_path: Path) -> None:
    db = tmp_path / "m.duckdb"
    with mod.database(db) as con:
        mod.init_schema(con)
    with mod.database(db, read_only=True) as con:
        assert mod.table_row_counts(con)["fact_daily"] == 0


def test_multiple_readers_coexist(tmp_path: Path) -> None:
    db = tmp_path / "m.duckdb"
    with mod.database(db) as con:
        mod.init_schema(con)
    with mod.database(db, read_only=True) as a, mod.database(db, read_only=True) as b:
        assert mod.table_row_counts(a)["fact_daily"] == 0
        assert mod.table_row_counts(b)["fact_daily"] == 0


def test_same_process_rw_connections_share_instance(tmp_path: Path) -> None:
    """DuckDB 同进程内对同一文件多次 connect 会共享实例，不会锁冲突。"""
    db = tmp_path / "m.duckdb"
    with mod.database(db) as con:
        mod.init_schema(con)
        with mod.database(db) as con2:
            assert mod.installed_version(con2) == mod.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# _scalar
# ---------------------------------------------------------------------------
def test_scalar_returns_first_value(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        assert mod._scalar(con, "SELECT 42") == 42


def test_scalar_with_params(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        assert mod._scalar(con, "SELECT ?::INTEGER + 1", [41]) == 42


def test_scalar_raises_when_no_row(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        mod.init_schema(con)
        with pytest.raises(mod.SchemaError, match="未返回任何行"):
            mod._scalar(con, "SELECT ts_code FROM fact_daily WHERE 1 = 0")


def test_scalar_propagates_closed_connection(tmp_path: Path) -> None:
    con = mod.connect(tmp_path / "m.duckdb")
    con.close()
    with pytest.raises(duckdb.Error):
        mod._scalar(con, "SELECT 1")


# ---------------------------------------------------------------------------
# table_row_counts
# ---------------------------------------------------------------------------
def test_table_row_counts_before_init_returns_minus_one(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        counts = mod.table_row_counts(con)
    assert set(counts) == {t.name for t in mod.TABLES}
    assert all(v == -1 for v in counts.values())


def test_table_row_counts_after_init_returns_zero(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        mod.init_schema(con)
        counts = mod.table_row_counts(con)

    assert counts["meta_schema_version"] == 1
    business = {k: v for k, v in counts.items() if k != "meta_schema_version"}
    assert all(v == 0 for v in business.values()), business


def test_table_row_counts_reflects_inserts(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        mod.init_schema(con)
        con.executemany(
            "INSERT INTO fact_daily (ts_code, trade_date, close) VALUES (?, ?, ?)",
            [
                ["000001.SZ", "2024-01-02", 10.5],
                ["000001.SZ", "2024-01-03", 10.8],
                ["600000.SH", "2024-01-02", 7.1],
            ],
        )
        counts = mod.table_row_counts(con)
    assert counts["fact_daily"] == 3
    assert counts["fact_adj_factor"] == 0
    assert counts["dim_stock_basic"] == 0


def test_table_row_counts_ignores_foreign_table(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        mod.init_schema(con)
        con.execute("CREATE TABLE user_scratch (x INTEGER)")
        counts = mod.table_row_counts(con)
    assert "user_scratch" not in counts
    assert set(counts) == {t.name for t in mod.TABLES}


def test_table_row_counts_ignores_views(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        mod.init_schema(con)
        counts = mod.table_row_counts(con)
    assert "v_daily_qfq" not in counts
    assert "v_daily_hfq" not in counts


def test_pylance_optional_subscript_regression(tmp_path: Path) -> None:
    """结果类型必须是 dict[str, int]，不得混入 None / bool"""
    with mod.database(tmp_path / "m.duckdb") as con:
        mod.init_schema(con)
        counts = mod.table_row_counts(con)
    for name, value in counts.items():
        assert isinstance(name, str)
        assert isinstance(value, int)
        assert not isinstance(value, bool)


# ---------------------------------------------------------------------------
# installed_version
# ---------------------------------------------------------------------------
def test_installed_version_none_when_row_absent(tmp_path: Path) -> None:
    with mod.database(tmp_path / "m.duckdb") as con:
        mod.init_schema(con)
        con.execute("DELETE FROM meta_schema_version WHERE component = 'warehouse'")
        assert mod.installed_version(con) is None


def test_installed_version_before_init_raises(tmp_path: Path) -> None:
    """未 init 时 meta_schema_version 不存在 → fail-fast 上抛，不返回 None"""
    with mod.database(tmp_path / "m.duckdb") as con, pytest.raises(duckdb.Error):
        mod.installed_version(con)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_exit_codes(tmp_path: Path) -> None:
    db = tmp_path / "m.duckdb"
    assert mod.main(["init", "--db", str(db)]) == 0
    assert mod.main(["check", "--db", str(db)]) == 0
    assert mod.main(["init", "--db", str(db), "--memory-limit", "4G"]) == 2
    assert mod.main(["check", "--db", str(tmp_path / "absent.duckdb")]) == 1


@pytest.mark.parametrize("bad", ["4GB'", "4GB\\", "4GB --"])
def test_cli_rejects_injection_attempt(tmp_path: Path, bad: str) -> None:
    assert (
        mod.main(["init", "--db", str(tmp_path / "m.duckdb"), "--memory-limit", bad])
        == 2
    )
