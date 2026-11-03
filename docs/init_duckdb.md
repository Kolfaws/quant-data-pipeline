# init_duckdb — DuckDB 量化库结构初始化

一个只做三件事的模块：**建表、建视图、校验结构**。不负责数据摄入，不修改既有数据，用于在数据管道启动前把库结构准备到“可用且可验证”的状态。

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

Detailed：

1. **只做结构**。`init_schema` 不写入任何业务数据，只建表、建视图、记录版本号。
2. **连接由调用方持有**。`init_schema(con)` 接收外部连接，**不关闭它**；连接的生命周期由 `connect()` / `database()` 或调用方自己管理。
3. **幂等**。重复 `init` 不重复建表、不重复版本行（`ON CONFLICT DO UPDATE`）。
4. **单事务**。DDL、视图、版本写入、校验在同一事务里，失败整体回滚。
5. **结构漂移即失败**。`verify_schema` 拒绝缺表、缺列、类型不符、**多余列**；结构变更必须走迁移并升级 `SCHEMA_VERSION`。
6. **单写者（跨进程）**。同一个库文件同一时刻只允许一个 RW 连接；只读连接可并存。DuckDB 的锁是**跨进程**的，同进程多连接会共享实例。

## 1.2 CLI Conventions

```bash
python init_duckdb.py init  --db data/market.duckdb
python init_duckdb.py check --db data/market.duckdb

python init_duckdb.py init \
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
| `--memory-limit` | `6GB` | 匹配 `^\d+(\.\d+)?(?:MB | GB | TB)$`（**不允许中间空格**） |
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
import init_duckdb as mod

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
| `installed_version(con)` | 返回 `warehouse` 组件版本号，无行返回 `None`，表不存在抛 `duckdb.Error` |
| `table_row_counts(con)` | 各表行数；表不存在记 `-1`；视图与非 `TABLES` 表不参与 |
| `_scalar(con, sql, params=())` | 单值查询；无结果行抛 `SchemaError` |

异常：

| 异常 | 触发条件 |
| --- | --- |
| `ConfigError(ValueError)` | `threads` 非法、`memory_limit` 格式非法 |
| `SchemaError(RuntimeError)` | 结构不一致（缺表 / 缺列 / 类型不符 / 多余列）、`_scalar` 查询无行 |
| `duckdb.Error` | DuckDB 自身错误，原样上抛 |

## 1.4 并发与生命周期 Conventions

- **同进程**：同一路径多次 `connect()` 会共享实例，**不会**锁冲突（`test_same_process_rw_connections_share_instance`）。
- **跨进程**：同一库文件第二个 RW 连接会报锁错误；只读连接可多个并存。
- **`init_schema` 不关闭连接**：内部用 `BEGIN / COMMIT / ROLLBACK` 显式事务，**不用 `with con:`**（DuckDB 的 `with con:` 语义是关闭连接，不是提交事务）。
- **连接构造失败自动关闭**：`connect()` 内部异常时 `con.close()` 后 re-raise，不泄漏句柄。

## 1.5 安全 Conventions

| 项 | 措施 |
| --- | --- |
| 参数注入 | `threads` 强类型校验；`memory_limit` 正则强校验；`temp_directory` 路径用 `_quote_literal` 转义单引号 |
| 文件权限（POSIX） | 库目录 `0700`、库文件 `0600`、临时目录 `0700`；每次 `connect()` 重新收紧库文件 |
| 权限失败不阻断 | `_chmod_quiet` 只 `LOG.debug`，不抛异常（Windows / 非 owner 场景） |
| 只读保护 | `read_only=True` 时不做 chmod、不写任何东西 |

---

END OF FILE
