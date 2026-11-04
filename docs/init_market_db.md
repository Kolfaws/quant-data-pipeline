# init_market_db — market DuckDB 基础数据库结构初始化

该模块只负责三件事：建表、建视图、校验结构。不负责数据摄入，不修改既有数据，用于在数据管道启动前把库结构准备到可用且可验证的状态。

- **Schema 版本**：`1.1.0`
- **默认库路径**：来自 `src.data_pipeline.config.DUCKDB_PATH`，回退 `data/market.duckdb`
- **默认资源**：`threads=6`、`memory_limit="6GB"`

---

# 1. Fundamental Conventions

## 1.1 Core Conventions

```text
Rules:       只建表、建视图、校验结构
Constraints: import 本模块 -> connect()/database() 拿连接 -> init_schema(con) 一次
```

详细约定：

1. **只做结构**。`init_schema` 不写入任何业务数据，只建表、建视图、记录版本号。
2. **连接由调用方持有**。`init_schema(con)` 接收外部连接，不关闭它；连接的生命周期由 `connect()` / `database()` 或调用方自己管理。
3. **幂等**。重复 `init` 不重复建表、不重复版本行（`ON CONFLICT DO UPDATE`）。
4. **单事务**。DDL、视图、版本写入、校验在同一事务里，失败整体回滚。
5. **结构漂移即失败**。`verify_schema` 拒绝缺表、缺列、类型不符、多余列；结构变更必须走迁移并升级 `SCHEMA_VERSION`。
6. **单写者（跨进程）**。同一个库文件同一时刻只允许一个 RW 连接；只读连接可并存。DuckDB 的锁是跨进程的，同进程多连接会共享实例。

## 1.2 CLI Conventions

```bash
python init_market_db.py init  --db data/market.duckdb
python init_market_db.py check --db data/market.duckdb

python init_market_db.py init \
  --db data/market.duckdb \
  --threads 6 \
  --memory-limit 6GB \
  --temp-dir /tmp/duck_spill \
  --log-level INFO
```

| 参数 | 默认 | 约束 |
| --- | --- | --- |
| `command` | `init` | `init` / `check` |
| `--db` | config 的 `DUCKDB_PATH` | 文件路径或 `:memory:` |
| `--threads` | `6` | `int`，`[1, 128]`，拒绝 `bool` |
| `--memory-limit` | `6GB` | 匹配 `^\d+(\.\d+)?(?:MB | GB | TB)$`（不允许中间空格） |
| `--temp-dir` | 无 | 目录会被 `mkdir(mode=0700)` |
| `--log-level` | config 的 `LOG_LEVEL` | `DEBUG / INFO / WARNING / ERROR` |

**退出码**：

| 码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `1` | `duckdb.Error` 或 `SchemaError` |
| `2` | `ConfigError`（参数非法） |

## 1.3 Python API Conventions

```python
import init_market_db as mod

# 推荐：上下文管理器，退出即关闭
with mod.database("data/market.duckdb") as con:
    mod.init_schema(con)
    print(mod.installed_version(con))    # "1.1.0"
    print(mod.table_row_counts(con))

# 只读复用
with mod.database("data/market.duckdb", read_only=True) as con:
    mod.verify_schema(con)

# 手动管理
con = mod.connect("data/market.duckdb", threads=8, memory_limit="8GB")
try:
    mod.init_schema(con)
finally:
    con.close()
```

公开接口：

| 函数 | 作用 |
| --- | --- |
| `connect(db_path, *, threads, memory_limit, temp_dir, read_only)` | 打开/创建连接，配置资源，返回连接 |
| `database(...)` | 上下文管理器版本 |
| `init_schema(con, *, verify=True)` | 建表 + 建视图 + 写版本 + 可选校验（单事务） |
| `verify_schema(con)` | 比对实际结构与 `TABLES`，不一致抛 `SchemaError` |
| `installed_version(con, component='warehouse')` | 返回指定组件版本；默认 `warehouse`；行不存在返回 `None`，表不存在抛 `duckdb.Error` |
| `table_row_counts(con)` | 各表行数；表不存在记 `-1`；视图与非 `TABLES` 表不参与 |
| `_scalar(con, sql, params=())` | 单值查询；无结果行抛 `SchemaError` |

异常：

| 异常 | 触发条件 |
| --- | --- |
| `ConfigError(ValueError)` | `threads` 非法、`memory_limit` 格式非法 |
| `SchemaError(RuntimeError)` | 结构不一致（缺表 / 缺列 / 类型不符 / 多余列）、`_scalar` 查询无行 |
| `duckdb.Error` | DuckDB 自身错误，原样上抛 |

## 1.4 并发与生命周期 Conventions

- **同进程**：同一路径多次 `connect()` 会共享实例，不会锁冲突（`test_same_process_rw_connections_share_instance`）。
- **跨进程**：同一库文件第二个 RW 连接会报锁错误；只读连接可多个并存。
- **`init_schema` 不关闭连接**：内部用 `BEGIN / COMMIT / ROLLBACK` 显式事务，不用 `with con:`（DuckDB 的 `with con:` 语义是关闭连接，不是提交事务）。
- **连接构造失败自动关闭**：`connect()` 内部异常时 `con.close()` 后 re-raise，不泄漏句柄。

## 1.5 安全 Conventions

| 项 | 措施 |
| --- | --- |
| 参数注入 | `threads` 强类型校验；`memory_limit` 正则强校验；`temp_directory` 路径用 `_quote_literal` 转义单引号 |
| 文件权限（POSIX） | 库目录 `0700`、库文件 `0600`、临时目录 `0700`；每次 `connect()` 重新收紧库文件 |
| 权限失败不阻断 | `_chmod_quiet` 只 `LOG.debug`，不抛异常（Windows / 非 owner 场景） |
| 只读保护 | `read_only=True` 时不做 chmod、不写任何东西 |

---

# 2. Database Schema

`SCHEMA_VERSION = "1.1.0"`。共 8 张表 + 2 个视图。

## 2.1 Overview

| # | 对象 | 类型 | 主键 |
| --- | --- | --- | --- |
| 1 | `meta_schema_version` | 表 | `component` |
| 2 | `meta_ingest_log` | 表 | `(table_name, scope_key)` |
| 3 | `dim_stock_basic` | 表 | 无 |
| 4 | `dim_trade_cal` | 表 | 无 |
| 5 | `fact_daily` | 表 | 无 |
| 6 | `fact_adj_factor` | 表 | 无 |
| 7 | `fact_daily_basic` | 表 | 无 |
| 8 | `fact_stk_limit` | 表 | 无 |
| 9 | `v_daily_qfq` | 视图 | — |
| 10 | `v_daily_hfq` | 视图 | — |

## 2.2 `meta_schema_version` — schema 版本记录

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `component` | `VARCHAR` | `NOT NULL` | 组件名；warehouse 固定 `'warehouse'`，factor 组件为 `'factor'` |
| `version` | `VARCHAR` | `NOT NULL` | schema 版本号，当前 `1.1.0` |
| `applied_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT current_timestamp` | 版本生效时间 |

约束：`PRIMARY KEY (component)`

## 2.3 `meta_ingest_log` — 摄入批次日志

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `table_name` | `VARCHAR` | `NOT NULL` | 目标表名 |
| `scope_key` | `VARCHAR` | `NOT NULL` | 批次范围键 |
| `row_count` | `BIGINT` | `NOT NULL DEFAULT 0` | 本批写入行数 |
| `status` | `VARCHAR` | `NOT NULL` | 批次状态 |
| `detail` | `VARCHAR` | 可空 | 附加信息 |
| `started_at` | `TIMESTAMPTZ` | `NOT NULL` | 开始时间 |
| `finished_at` | `TIMESTAMPTZ` | 可空 | 结束时间 |

约束：`PRIMARY KEY (table_name, scope_key)`

## 2.4 `dim_stock_basic` — 股票基础信息

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `ts_code` | `VARCHAR` | `NOT NULL` | 股票代码 |
| `symbol` | `VARCHAR` | 可空 | 交易代码 |
| `name` | `VARCHAR` | 可空 | 名称 |
| `area` | `VARCHAR` | 可空 | 地域 |
| `industry` | `VARCHAR` | 可空 | 行业 |
| `market` | `VARCHAR` | 可空 | 市场 |
| `exchange` | `VARCHAR` | 可空 | 交易所 |
| `list_status` | `VARCHAR` | `NOT NULL` | 上市状态 |
| `list_date` | `DATE` | 可空 | 上市日期 |
| `delist_date` | `DATE` | 可空 | 退市日期 |
| `is_hs` | `VARCHAR` | 可空 | 是否沪深港通标的 |

## 2.5 `dim_trade_cal` — 交易日历

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `exchange` | `VARCHAR` | `NOT NULL` | 交易所 |
| `cal_date` | `DATE` | `NOT NULL` | 日历日期 |
| `is_open` | `BOOLEAN` | `NOT NULL` | 是否交易日 |
| `pretrade_date` | `DATE` | 可空 | 上一交易日 |

## 2.6 `fact_daily` — 日线行情

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `ts_code` | `VARCHAR` | `NOT NULL` | 股票代码 |
| `trade_date` | `DATE` | `NOT NULL` | 交易日 |
| `open` | `DOUBLE` | 可空 | 开盘价 |
| `high` | `DOUBLE` | 可空 | 最高价 |
| `low` | `DOUBLE` | 可空 | 最低价 |
| `close` | `DOUBLE` | 可空 | 收盘价 |
| `pre_close` | `DOUBLE` | 可空 | 昨收价 |
| `chg` | `DOUBLE` | 可空 | 涨跌额 |
| `pct_chg` | `DOUBLE` | 可空 | 涨跌幅 |
| `vol` | `DOUBLE` | 可空 | 成交量 |
| `amount` | `DECIMAL(20,4)` | 可空 | 成交额 |

## 2.7 `fact_adj_factor` — 复权因子

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `ts_code` | `VARCHAR` | `NOT NULL` | 股票代码 |
| `trade_date` | `DATE` | `NOT NULL` | 交易日 |
| `adj_factor` | `DOUBLE` | 可空 | 复权因子 |

## 2.8 `fact_daily_basic` — 每日指标

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `ts_code` | `VARCHAR` | `NOT NULL` | 股票代码 |
| `trade_date` | `DATE` | `NOT NULL` | 交易日 |
| `turnover_rate` | `DOUBLE` | 可空 | 换手率 |
| `turnover_rate_f` | `DOUBLE` | 可空 | 自由流通换手率 |
| `volume_ratio` | `DOUBLE` | 可空 | 量比 |
| `pe` | `DOUBLE` | 可空 | 市盈率 |
| `pe_ttm` | `DOUBLE` | 可空 | 市盈率（TTM） |
| `pb` | `DOUBLE` | 可空 | 市净率 |
| `ps` | `DOUBLE` | 可空 | 市销率 |
| `ps_ttm` | `DOUBLE` | 可空 | 市销率（TTM） |
| `dv_ratio` | `DOUBLE` | 可空 | 股息率 |
| `dv_ttm` | `DOUBLE` | 可空 | 股息率（TTM） |
| `total_share` | `DOUBLE` | 可空 | 总股本 |
| `float_share` | `DOUBLE` | 可空 | 流通股本 |
| `free_share` | `DOUBLE` | 可空 | 自由流通股本 |
| `total_mv` | `DECIMAL(20,4)` | 可空 | 总市值 |
| `circ_mv` | `DECIMAL(20,4)` | 可空 | 流通市值 |

## 2.9 `fact_stk_limit` — 每日涨跌停价

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `ts_code` | `VARCHAR` | `NOT NULL` | 股票代码 |
| `trade_date` | `DATE` | `NOT NULL` | 交易日 |
| `pre_close` | `DOUBLE` | 可空 | 昨收价 |
| `up_limit` | `DOUBLE` | 可空 | 涨停价 |
| `down_limit` | `DOUBLE` | 可空 | 跌停价 |

## 2.10 `v_daily_qfq` — 前复权日线

数据来源：`fact_daily d JOIN fact_adj_factor f ON f.ts_code = d.ts_code AND f.trade_date = d.trade_date`

复权基准：每只股票 `last_adj = arg_max(adj_factor, trade_date)`

价格变换：`price × adj_factor / adj_last`

输出列：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ts_code` | `VARCHAR` | 股票代码 |
| `trade_date` | `DATE` | 交易日 |
| `open` / `high` / `low` / `close` | `DOUBLE` | 前复权价 |
| `pre_close` | `DOUBLE` | 前复权前收 |
| `chg` | `DOUBLE` | 前复权涨跌额 |
| `pct_chg` | `DOUBLE` | 保持原值 |
| `vol` | `DOUBLE` | 保持原值 |
| `amount` | `DECIMAL(20,4)` | 前复权重算成交额 |
| `adj_factor` | `DOUBLE` | 复权因子 |

## 2.11 `v_daily_hfq` — 后复权日线

数据来源：同 `v_daily_qfq`

价格变换：`price × adj_factor`

输出列：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ts_code` | `VARCHAR` | 股票代码 |
| `trade_date` | `DATE` | 交易日 |
| `open` / `high` / `low` / `close` | `DOUBLE` | 后复权价 |
| `pre_close` | `DOUBLE` | 后复权前收 |
| `vol` | `DOUBLE` | 保持原值 |
| `amount` | `DECIMAL(20,4)` | 后复权重算成交额 |
| `adj_factor` | `DOUBLE` | 复权因子 |

注意：`v_daily_hfq` 不输出 `chg` 与 `pct_chg`。

## 2.12 类型与命名约定

| 约定 | 内容 |
| --- | --- |
| 代码类字段 | `VARCHAR` |
| 日期类字段 | `DATE` |
| 时间戳字段 | `TIMESTAMPTZ`（内部归一化为 `TIMESTAMP WITH TIME ZONE`） |
| 金额字段 | `DECIMAL(20,4)` |
| 价格 / 比率 / 数量 | `DOUBLE` |
| 布尔字段 | `BOOLEAN` |
| 命名前缀 | `meta_` / `dim_` / `fact_` / `v_` |

---

# 3. Explanation of Implementation

## 3.1 `connect()` — 连接构造

流程：

1. 校验 `threads`（`int`，非 `bool`，`[1,128]`）与 `memory_limit`（正则）。
2. 非内存库时 `path.parent.mkdir(parents=True, mode=0o700)`。
3. `duckdb.connect(target, read_only=...)`。
4. 在 `try/except` 中执行一组 `SET`：
   - `SET threads = N`（已强校验，无注入）
   - `SET memory_limit = '...'`（正则强校验）
   - `SET preserve_insertion_order = false`（降低大写入内存峰值）
   - `SET enable_progress_bar = false`
   - 若给了 `temp_dir`：`mkdir(mode=0o700)` + `SET temp_directory = '...'`（单引号转义）
5. 构造期任意异常 → `con.close()` 后 re-raise，不泄漏句柄。
6. 非内存库且非只读 → `chmod(0600)`（`_chmod_quiet` 失败只 `debug`）。

`database()` 是对 `connect()` 的 `@contextmanager` 包装，`finally` 里 `close()` 并吞掉关闭异常（记 `warning`），避免掩盖业务异常。

## 3.2 `init_schema()` — 单事务流程

关键点：不使用 `with con:`。DuckDB 的 `DuckDBPyConnection.__exit__` 语义是关闭连接，而 `init_schema` 接收的是调用方连接，不能替调用方关闭。改用显式事务：

```python
con.execute("BEGIN TRANSACTION")
try:
    for table in TABLES:
        con.execute(table.ddl())          # 1. 建表（IF NOT EXISTS）

    if verify:
        verify_schema(con)                # 2. 先校验，残缺表在此抛 SchemaError

    for name, sql in VIEWS.items():
        con.execute(f'CREATE OR REPLACE VIEW "{name}" AS {sql}')  # 3. 视图

    con.execute(
        "INSERT INTO meta_schema_version (component, version) "
        "VALUES ('warehouse', ?) "
        "ON CONFLICT (component) DO UPDATE SET "
        "version = excluded.version, applied_at = now()",       # 4. 版本 upsert
        [SCHEMA_VERSION],
    )
    con.execute("COMMIT")
except Exception:
    con.execute("ROLLBACK")
    raise
```

顺序设计的原因：

- **先校验、后建视图**：视图 SQL 依赖表结构（`d.open` 等）。若表已存在但残缺，先建视图会抛 `BinderException`，`SchemaError` 就无法按预期暴露。把 `verify_schema` 放在建表后、建视图前，残缺表会以 `SchemaError` 形式暴露，错误信息带表名。
- **版本行用 `now()`**：`current_timestamp` 在 `ON CONFLICT DO UPDATE SET applied_at = current_timestamp` 上下文里会被 DuckDB 解析为列引用而报 `BinderException`，必须换成 `now()`。
- **单事务**：任何一步失败整体回滚，不会留下建了半张表的中间态。

`Table.ddl()` 生成 `CREATE TABLE IF NOT EXISTS`，所以重复执行幂等；版本行 `ON CONFLICT DO UPDATE` 保证只有一行（测试 `test_init_does_not_duplicate_version_rows` 三连 `init` 后断言 `count(*) == 1`）。

## 3.3 `verify_schema()` — 结构比对

1. 从 `duckdb_columns()` 拉 `schema_name = 'main'` 的全部 `(table_name, column_name, data_type)`。
2. 构建 `actual: dict[str, dict[str, str]]`，`data_type` 经 `_normalise_type` 归一化（`TIMESTAMPTZ` → `TIMESTAMP WITH TIME ZONE`）。
3. 对 `TABLES` 里每张表：
   - 缺表 → `缺表 <name>`；
   - 缺列 → `<table>.<column> 缺失`；
   - 类型不符 → `<table>.<column> 类型 <got> != <want>`；
   - 多余列 → `<table> 存在多余列 [...]`。
4. 有问题就拼成一条消息抛 `SchemaError`，前缀 “schema 校验失败（请勿直接修改建表语句，需走迁移）”。

**为什么拒绝多余列**：允许加列会让代码定义的结构和实际结构长期漂移，`verify_schema` 失去意义。任何结构变化必须升级 `SCHEMA_VERSION` 并写迁移。

## 3.4 版本记录

- 表 `meta_schema_version(component, version, applied_at)`，主键 `component`。
- `init_schema` 只 upsert `component = 'warehouse'` 一行；factor 组件会写入 `component = 'factor'` 行，与 warehouse 行并存，互不覆盖。
- `installed_version(con, component='warehouse')` 返回指定组件的 `version`；行不存在返回 `None`；表不存在直接抛 `duckdb.Error`（fail-fast，不静默）。
- 组件名走 `_validate_component()` 白名单校验，并以参数绑定传入 SQL。
- market 的 `verify_schema` / `table_row_counts` 仍只覆盖 warehouse 的 `TABLES`；factor 表作为额外对象被忽略，不会导致 market 校验失败。

## 3.5 `table_row_counts()` — 状态打印

1. 从 `duckdb_tables()` 拿 `main` 下所有表名。
2. 对 `TABLES` 里每张表：
   - 不在 actual 里 → `-1`；
   - 在 → `SELECT count(*)`，结果转 `int`。
3. 只返回 `TABLES` 里定义的表，视图不参与，用户自建表被忽略。

用于 CLI 初始化后打印状态，以及 `test_table_row_counts_*` 系列。

注意：`meta_schema_version` 在 `init` 后是 `1` 行（版本记录），其余业务表是 `0`。`test_table_row_counts_after_init_returns_zero` 已按此修正。

## 3.6 `_scalar()` — 单值查询

```python
cursor = con.execute(sql, list(params)) if params else con.execute(sql)
row = cursor.fetchone()
if row is None:
    raise SchemaError(f"查询未返回任何行：{sql}")
return row[0]
```

- 有 `params` 时走参数绑定，无 `params` 时直接执行（避免 DuckDB 对空参数列表的边界行为）。
- **无结果行抛 `SchemaError`**，而不是返回 `None`。调用方（`table_row_counts` 等）都默认有结果，静默 `None` 会把结构问题掩盖成下游 `NoneType` 错误。
- 连接已关闭时 `con.execute` 抛 `duckdb.Error`，原样上抛。

## 3.7 CLI 与日志

- `build_parser()` 定义 `init` / `check` 与资源参数。
- `_setup_logging()` 清空 root handlers，挂一个 stderr handler，级别取自 `--log-level`（默认来自 config 的 `LOG_LEVEL`）。
- `main()` 捕获三类异常：`ConfigError → 2`、`duckdb.Error → 1`、`SchemaError → 1`，其余上抛。
- 成功后打印 `初始化/校验 完成 db=... version=...`，并逐表打印行数。

## 3.8 配置加载

`_load_config_defaults()` 在函数内做 `sys.path` 注入与 import：

1. `root_dir = Path(__file__).resolve().parent.parent`（要求 `init_market_db.py` 位于 `src/` 下）；
2. `from src.data_pipeline.config import DUCKDB_PATH, LOG_LEVEL`；
3. `DUCKDB_PATH` 为空 → 回退 `data/market.duckdb`；
4. `ImportError` / `ModuleNotFoundError` → 整体回退 `data/market.duckdb` / `INFO`。

放在函数内而不是 module 顶层，是为了避免 import 本模块时污染 `sys.path`，也避免 config 不可用时 import 直接失败。

> 注意：`threads` / `memory_limit` 不从 config 读，只走 CLI 或显式传参。

## 3.9 测试覆盖

```bash
pytest -q scripts/test_init_market_db.py
# 预期：41 passed, 3 skipped（POSIX 权限测试在 Windows 上跳过）
```

| 类别 | 用例 |
| --- | --- |
| 建表 / 视图 | `test_init_creates_tables_and_views` |
| 幂等 / 版本唯一 | `test_init_is_idempotent`、`test_init_does_not_duplicate_version_rows` |
| 结构漂移 | `test_verify_detects_schema_drift`、`test_verify_detects_extra_column` |
| memory_limit | `test_memory_limit_accepts_valid`、`test_memory_limit_takes_effect`、`test_memory_limit_rejects_invalid`（含 `4 GB`） |
| threads | `test_threads_out_of_range`、`test_threads_rejects_bool` |
| 文件权限（POSIX） | `test_file_permissions`、`test_permissions_restored_on_reconnect` |
| temp_dir | `test_temp_dir_created_and_escaped`（含单引号）、`test_temp_dir_permissions` |
| 只读 / 并发 | `test_read_only_connection_can_query`、`test_multiple_readers_coexist`、`test_same_process_rw_connections_share_instance` |
| `_scalar` | 返回值、参数绑定、无行抛错、关闭连接上抛 |
| `table_row_counts` | 未 init 全 `-1`、init 后版本表 `1` 其余 `0`、插入后反映、忽略外部表 / 视图、类型纯净 |
| `installed_version` | 行缺失返回 `None`、未 init 抛 `duckdb.Error` |
| CLI | `test_cli_exit_codes`、`test_cli_rejects_injection_attempt` |

关于 `test_second_writer_is_rejected`：DuckDB 的写锁是跨进程的，同进程内多连接会共享实例、不会失败，所以该测试已改名为 `test_same_process_rw_connections_share_instance`，验证同进程共享实例这一真实行为；跨进程单写者契约由 DuckDB 自身保证。

---

## Appendix: Edition History

| 版本 | 变更 |
| --- | --- |
| `1.1.0` | 新增 `v_daily_qfq` / `v_daily_hfq` 视图；`TIMESTAMPTZ` 归一化；`_scalar` 无行抛 `SchemaError`；CLI 退出码 0/1/2；`init_schema` 改显式事务；`verify_schema` 提前到建视图前；版本 upsert 用 `now()`；`memory_limit` 正则禁止中间空格 |
| `1.0.0` | 初始 schema（8 张表 + 版本记录 + 幂等初始化） |

---

END OF FILE
