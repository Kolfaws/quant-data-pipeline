# init_factor_db — factor DuckDB 组件结构初始化

在已有 `warehouse` 组件之上追加 `factor` 组件：只建 factor 表、视图、写 factor 版本行，不重建行情表，不写入业务数据。

- **Schema 版本**：`1.2.0`
- **组件名**：`factor`
- **库文件**：与 `warehouse` 同库；路径来自 `data_pipeline.config.DUCKDB_PATH`，推荐 `${MARKET_DB_PATH}`
- **DDL 来源**：`quant_schema.market_ddl.FACTOR_TABLES / FACTOR_STATIC_VIEWS`
- **依赖**：`init_market_db` 必须先执行，且 warehouse 版本 `>= 1.1.0`（当前 1.3.0）
- **资源**：沿用 `threads=6`、`memory_limit="6GB"`

> `FACTOR_DB_PATH` 已废弃。factor 与 warehouse 必须同库，`v_factor_valid` 才能直接 JOIN。
> 若确需独立文件，必须 `ATTACH` 行情库并改写全部视图，超出本模块范围。

---

## 1. Conventions

### 1.1 Core

1. **只做结构**：`init_schema` 不写因子值、不派生可交易性、不改行情表。
2. **同一 DuckDB 文件**：warehouse 与 factor 共享 `meta_schema_version` / `meta_ingest_log`。
3. **单写者**：跨进程同一时刻只允许一个 RW 连接；`init_market_db` 与 `init_factor_db` 必须串行执行。
4. **共享表 DDL 逐字一致**：factor 直接复用 market 的 `Table` 对象，不复制 SQL。
5. **单事务**：建表、校验、建视图、版本 upsert 同事务；失败整体 `ROLLBACK`。
6. **结构漂移即失败**：缺表、缺列、类型不符、多余列均抛 `SchemaError`。
7. **先校验后建视图**：残缺表以 `SchemaError` 暴露，而不是视图绑定的 `BinderException`。
8. **版本隔离**：`meta_schema_version` 中 warehouse 与 factor 各一行，互不覆盖。
9. **调用方持有连接**：`init_schema(con)` 不关闭 `con`；内部用显式 `BEGIN / COMMIT / ROLLBACK`，不用 `with con:`（DuckDB 的 `__exit__` 是关连接，不是提交事务）。

### 1.2 CLI

```bash
python scripts/init_market_db.py init    --db "${MARKET_DB_PATH}"
python scripts/init_factor_db.py init    --db "${MARKET_DB_PATH}"
python scripts/init_factor_db.py check   --db "${MARKET_DB_PATH}"
python scripts/init_factor_db.py refresh --db "${MARKET_DB_PATH}"

python scripts/init_factor_db.py init \
  --db "${MARKET_DB_PATH}" \
  --threads 6 \
  --memory-limit 6GB \
  --temp-dir /tmp/duck_spill \
  --log-level INFO
```

| 参数 | 默认 | 约束 |
| --- | --- | --- |
| `command` | `init` | `init` / `check` / `refresh` |
| `--db` | config `DUCKDB_PATH` | 文件路径或 `:memory:` |
| `--env` | `prod` | `prod` / `test`；未传 `--db` 时按环境选择路径 |
| `--threads` | `6` | `[1,128]`，拒绝 `bool` |
| `--memory-limit` | `6GB` | `^\d+(\.\d+)?(?:MB\|GB\|TB)$`（不允许中间空格） |
| `--temp-dir` | 无 | 目录会被 `mkdir(mode=0700)` |
| `--log-level` | config `LOG_LEVEL` | `DEBUG / INFO / WARNING / ERROR` |

`refresh` 用于因子目录（`meta_factor_registry`）新增或停用因子后重建 `v_factor_wide`。

退出码：

| 码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `1` | `duckdb.Error` 或 `SchemaError` |
| `2` | `ConfigError`（参数非法） |

### 1.3 Python API

```python
import init_market_db as market
import init_factor_db as factor

with market.database("${MARKET_DB_PATH}") as con:
    market.init_schema(con)                            # 必须先执行
    factor.init_schema(con)                            # 追加 factor 组件
    print(factor.installed_version(con))               # "1.2.0"
    print(factor.installed_version(con, "warehouse"))  # "1.3.0"
    print(factor.table_row_counts(con))

# 因子目录变更后重建宽表视图
with factor.database("${MARKET_DB_PATH}") as con:
    factor.refresh_views(con)
```

| 函数 | 作用 |
| --- | --- |
| `connect(...)` / `database(...)` | 复用 market 的连接器与资源限制 |
| `init_schema(con, *, verify=True)` | 建共享/factor 表、校验、建视图、写 factor 版本（单事务） |
| `verify_schema(con, *, verify_views=True)` | 校验依赖 + 共享表 + factor 表，可选校验视图 |
| `installed_version(con, component="factor")` | 返回指定组件版本；行不存在返回 `None` |
| `table_row_counts(con)` | 统计 factor 模块 `TABLES`（含共享表）；缺失表记 `-1` |
| `refresh_views(con)` | 按当前活跃因子重建两个视图 |
| `_scalar(con, sql, params=())` | 单值查询；无结果行抛 `SchemaError` |

异常：

| 异常 | 触发条件 |
| --- | --- |
| `ConfigError(ValueError)` | `threads` / `memory_limit` / `component` 非法 |
| `SchemaError(RuntimeError)` | warehouse 缺失或版本过低、缺表/缺列/类型漂移/多余列、缺视图 |
| `duckdb.Error` | DuckDB 自身错误，原样上抛 |

### 1.4 并发与生命周期

- **同进程**：同一路径多次 `connect()` 共享实例，不会锁冲突。
- **跨进程**：同一文件第二个 RW 连接被 DuckDB 拒绝；只读连接可多个并存。
- **不关闭调用方连接**：`init_schema` / `refresh_views` 都不关闭 `con`。
- **`refresh_views` 自开事务**：不能在调用方已开启的事务中调用，否则 `BEGIN` 会报错。
- **`database()` 退出即关闭**：关闭异常只记 `warning`，不掩盖业务异常。

### 1.5 安全

| 项 | 措施 |
| --- | --- |
| component 注入 | 正则 `^[a-z][a-z0-9_]{0,31}$` + 参数绑定 |
| 动态 SQL | PIVOT / 条件聚合只拼接 `int(factor_id)` |
| 视图名 | 仅取 `VIEW_NAMES` 常量，`DESCRIBE` 前强校验 |
| 文件权限 | 继承 market `connect()`：目录 `0700`、库文件 `0600`、临时目录 `0700` |
| 只读保护 | `read_only=True` 时不 chmod、不写任何东西 |
| 日志 | 只打印表名/行数/版本，不打印因子值、股票明细、token |
| 外部命令 | 无 shell、无 `eval/exec/pickle` |

---

## 2. Schema

`SCHEMA_VERSION = "1.2.0"`，`component = "factor"`。新增 7 张表 + 2 个视图，并把 2 张共享基础表纳入严格校验。

### 2.1 Overview

| # | 对象 | 类型 | 主键 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | `meta_schema_version` | 表 | `component` | 共享；factor 写一行 |
| 2 | `meta_ingest_log` | 表 | `(table_name, scope_key)` | 共享；批次日志 |
| 3 | `meta_factor_registry` | 表 | `factor_id` | 因子目录 |
| 4 | `fact_factor_daily` | 表 | `(ts_code, trade_date, factor_id)` | 因子值长表（主存储） |
| 5 | `fact_tradable_flag` | 表 | `(ts_code, trade_date)` | 日频可交易性标志（派生） |
| 6 | `fact_factor_quality` | 表 | `(factor_id, trade_date)` | 批次质量快照（可重建） |
| 7 | `meta_factor_profile` | 表 | `factor_id` | 因子域 / 频率 / 来源等元数据 |
| 8 | `meta_factor_validation` | 表 | `(factor_id, env, validated_at)` | 上线前验证记录 |
| 9 | `meta_factor_promotion_log` | 表 | `promotion_id` | test -> prod 发布审计 |
| 10 | `v_factor_wide` | 视图 | — | 动态 PIVOT 宽表 |
| 11 | `v_factor_valid` | 视图 | — | 可交易性 + `is_stale` 过滤 |

自 v1.2.0 起，所有业务表都显式声明主键。ART 索引会增加写入成本，但换来
“重复摄入/重复计算不可能产生重复行”，避免窗口函数静默错算；因子写入仍建议
按 `(factor_id, trade_date)` 区间 `DELETE + INSERT` 做整段替换。

### 2.2 `meta_factor_registry` — 因子目录

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `factor_id` | `INTEGER` | `NOT NULL` | 因子整数 ID，事实表外键 |
| `factor_name` | `VARCHAR` | `NOT NULL` | 唯一名，如 `mom_20d` |
| `factor_group` | `VARCHAR` | 可空 | momentum / value / quality / liquidity |
| `value_type` | `VARCHAR` | `NOT NULL` | raw / zscore / rank |
| `direction` | `SMALLINT` | `NOT NULL DEFAULT 1` | 1 正向，-1 反向 |
| `lookback_days` | `INTEGER` | 可空 | 回看窗口（天），供审计 |
| `formula_hash` | `VARCHAR` | 可空 | 因子逻辑版本指纹 |
| `description` | `VARCHAR` | 可空 | 描述 |
| `is_active` | `BOOLEAN` | `NOT NULL DEFAULT TRUE` | 是否启用，决定宽表列 |

约束：`PRIMARY KEY (factor_id)`、`UNIQUE (factor_name)`。

为什么用整数 `factor_id`：`fact_factor_daily.factor_id` 是行内高频重复列，`INTEGER`（4B）比因子名 `VARCHAR`（~12B）压缩率与扫描效率更好；且 `factor_name` 改名不影响历史值。

`formula_hash` 是鲁棒性关键：同一 `factor_id` 换了算法而不换 ID，会导致历史值口径混杂。管道写入前必须比对指纹，不一致时**拒绝写入并提示新开 `factor_id`**。本模块不强制该约束，只提供字段。

### 2.3 `fact_factor_daily` — 因子值长表

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `ts_code` | `VARCHAR` | `NOT NULL` | 股票代码 |
| `trade_date` | `DATE` | `NOT NULL` | 交易日 |
| `factor_id` | `INTEGER` | `NOT NULL` | 因子 ID |
| `value` | `DOUBLE` | 可空 | 因子值；`NULL` 表示缺失 |
| `is_stale` | `BOOLEAN` | `NOT NULL DEFAULT FALSE` | 是否 forward-fill |
| `source_batch_id` | `BIGINT` | 可空 | 关联 `meta_ingest_log` 批次 |

约束：`PRIMARY KEY (ts_code, trade_date, factor_id)`。

幂等写入建议：按 `(factor_id, trade_date 区间)` 先 `DELETE` 再 `INSERT`。
主键本身也能保证唯一，但区间替换语义更清晰，也能清掉本批次已不存在的成分。

`value` 与 `is_stale` 拆开的原因：停牌期间不应静默填充。若业务需要 forward-fill，填充值标 `is_stale = TRUE`，回测可用 `v_factor_valid` 过滤，避免虚假信号进入组合。

物理排序建议：写入时 `ORDER BY trade_date, ts_code`（或按日分批写入），让 zone map 在日期过滤上剪枝更有效。若团队以单股票时序研究为主，可改 `(ts_code, trade_date)`——选一种，不要混，否则 zone map 收益被稀释。

### 2.4 `fact_tradable_flag` — 可交易性标志

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `ts_code` | `VARCHAR` | `NOT NULL` |
| `trade_date` | `DATE` | `NOT NULL` |
| `is_suspended` | `BOOLEAN` | `NOT NULL` |
| `is_st` | `BOOLEAN` | `NOT NULL` |
| `is_limit_up` | `BOOLEAN` | `NOT NULL` |
| `is_limit_down` | `BOOLEAN` | `NOT NULL` |
| `is_buyable` | `BOOLEAN` | `NOT NULL` |
| `is_sellable` | `BOOLEAN` | `NOT NULL` |
| `in_universe` | `BOOLEAN` | `NOT NULL` |

**主键**：`(ts_code, trade_date)`。

派生 SQL（由因子管道执行，不由 init 模块执行）：

```sql
is_suspended   = (d.vol IS NULL OR d.vol = 0)
is_limit_up    = (d.close >= l.up_limit)   AND (d.trade_date > s.list_date)
is_limit_down  = (d.close <= l.down_limit) AND (d.trade_date > s.list_date)
in_universe    = (d.trade_date >= s.list_date)
             AND (s.delist_date IS NULL OR d.trade_date < s.delist_date)
is_buyable     = NOT is_suspended AND NOT is_limit_up   AND in_universe
is_sellable    = NOT is_suspended AND NOT is_limit_down AND in_universe
```

`list_date` 当日不应用涨跌停：A 股 IPO 首日通常不设涨跌幅限制，Tushare
`stk_limit` 在该日可能给出参考价，直接比较会把首日误判为涨跌停。

`is_st` 依赖日频 ST 快照。warehouse 当前只有 `dim_stock_basic.name` 的当前快照，这是已知局限。无法补日频 ST 时，factor 层先置 `FALSE`，并在 `meta_ingest_log.detail` 或质量表里记录「ST 未覆盖」——不要伪造历史 ST。

派生脚本：

```bash
# dry-run：只统计行数，不写库
python scripts/build_tradable_flags.py --start 2015-01-01 --end 2026-11-05

# 真正写入 fact_tradable_flag（幂等 upsert）
python scripts/build_tradable_flags.py --start 2015-01-01 --end 2026-11-05 --apply
```

`is_st` 当前统一写 `FALSE`；脚本会在 `fact_stk_limit` / `dim_stock_basic` 为空时给出 warning，
`in_universe` 在缺股票列表时退化为“fact_daily 出现即视为在池”。

### 2.5 `fact_factor_quality` — 批次质量快照

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `factor_id` | `INTEGER` | `NOT NULL` |
| `trade_date` | `DATE` | `NOT NULL` |
| `n_total` | `BIGINT` | `NOT NULL` |
| `n_valid` | `BIGINT` | `NOT NULL` |
| `n_stale` | `BIGINT` | `NOT NULL` |
| `n_outlier` | `BIGINT` | `NOT NULL` |
| `coverage` | `DOUBLE` | `NOT NULL` |
| `computed_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT now()` |

`coverage = n_valid / n_total`。建议闸门：`coverage < 0.8` 或 `n_outlier` 突增时告警。
**主键**：`(factor_id, trade_date)`；同一批次重跑会覆盖质量行，不追加。

### 2.6 `v_factor_wide` — 动态 PIVOT 宽表

按 `meta_factor_registry` 中 `is_active = TRUE` 的因子动态生成：

```sql
PIVOT fact_factor_daily
ON factor_id IN (1, 2, 3)
USING FIRST(value)
GROUP BY ts_code, trade_date
ORDER BY ts_code, trade_date;
```

- 列结构：`ts_code`、`trade_date`、每个活跃 `factor_id` 一列（列名为 ID 字符串）。
- 活跃因子为 0 时，视图只有前两列。
- PIVOT 在空表或旧版 DuckDB 上可能失败；模块自动回退到条件聚合 `FIRST(value) FILTER (WHERE factor_id = N)`，列数保持 `2 + 活跃因子数`。
- **视图列在创建时固定**：新增或停用因子后必须执行 `init_factor_db.py refresh` 或重跑 `init`，否则宽表列不更新。
- 仅作研究/导出；反复全量扫描建议把核心 10–20 个因子物化成 `fact_factor_core_wide`（按年重建），长尾留长表。

### 2.7 `v_factor_valid` — 消费视图

```sql
SELECT f.ts_code, f.trade_date, f.factor_id, f.value, f.is_stale
FROM fact_factor_daily f
JOIN fact_tradable_flag t
  ON t.ts_code = f.ts_code
 AND t.trade_date = f.trade_date
WHERE f.is_stale = FALSE
  AND (t.is_buyable = TRUE OR t.is_sellable = TRUE);
```

**语义边界**：

- `is_stale = FALSE` 是视图自身保证的：forward-fill 出来的陈旧值不会进入消费视图；调用方不需要再手动过滤。
- 该条件同时是「至少一个方向可交易」。涨停股 `is_buyable = FALSE` 但 `is_sellable = TRUE`，会被保留——因为对持仓方它是可卖的。
- 方向过滤必须由策略层完成：买入日加 `AND t.is_buyable`，卖出日加 `AND t.is_sellable`；或用 `fact_tradable_flag` 直接 join。
- 若上游 `fact_tradable_flag` 有重复 `(ts_code, trade_date)`，视图会放大行数；管道必须先按该键去重。

---

### 2.8 因子域、验证与发布

新增三张元数据表，不改动原 `meta_factor_registry`：

- `meta_factor_profile`：`domain`（`price_volume` / `fundamental` /
  `capital_flow` / `macro`）、`frequency`、`unit`、`source`、`owner`、`notes`；
- `meta_factor_validation`：`factor_id` + `env` + `status`
  （`pending` / `approved` / `rejected`）+ `metrics_json`；
- `meta_factor_promotion_log`：记录 test -> prod 的发布审计。

测试库和正式库使用同一套 DDL。测试库初始化：

```bash
python scripts/init_test_dbs.py
python scripts/sync_test_market.py --apply
```

研究验证通过后，由 quant-factor 的 `scripts/promote_test_factor.py` 发布：

```bash
python scripts/promote_test_factor.py --factor-id 101          # dry-run
python scripts/promote_test_factor.py --factor-id 101 --apply  # 写入正式库
```

发布前必须存在最新 `env='test'`、`status='approved'` 的验证记录。

## 3. 与 warehouse 的边界

### 3.1 分层职责

```text
warehouse（已有）                  factor（新增）
─────────────────                  ─────────────────
dim_stock_basic        ──┐
dim_trade_cal           │
fact_daily              ├──▶  fact_factor_daily
fact_adj_factor         │     meta_factor_registry
fact_daily_basic        │     fact_tradable_flag
fact_stk_limit        ──┘     fact_factor_quality
                              v_factor_wide / v_factor_valid
```

factor 层只读 warehouse 的表，只写自己的 `meta_factor_*` / `fact_factor_*` / `fact_tradable_flag` / `v_*`。不重建 `fact_daily` 等行情表，不改动其结构。

### 3.2 类型对齐（强制）

| 维度 | warehouse 约定 | factor 必须沿用 |
| --- | --- | --- |
| 代码 | `VARCHAR` | `VARCHAR`，join key 唯一 |
| 日期 | `DATE` | `DATE`，禁止 `TIMESTAMP` |
| 金额 | `DECIMAL(20,4)` | 中间计算转 `DOUBLE`，落库按需 |
| 价格/比率/数量 | `DOUBLE` | 因子值统一 `DOUBLE` |
| 布尔 | `BOOLEAN` | 同 |
| 时间戳 | `TIMESTAMPTZ` | `computed_at` 用 `TIMESTAMPTZ` |
| 命名前缀 | `meta_` / `dim_` / `fact_` / `v_` | 同，因子目录用 `meta_factor_registry` |

### 3.3 共享表与版本隔离

`meta_schema_version` / `meta_ingest_log` 的 DDL 直接从 `init_market_db.TABLES` 取 `Table` 对象，实现上不可能漂移；factor 的 `verify_schema` 仍会对实际库逐列严格比对。

版本行：

```sql
SELECT component, version FROM meta_schema_version ORDER BY component;
-- factor    1.2.0
-- warehouse 1.3.0
```

| 调用 | 默认 component | 说明 |
| --- | --- | --- |
| `init_market_db.installed_version(con)` | `warehouse` | 旧调用方零改动 |
| `init_factor_db.installed_version(con)` | `factor` | 查 factor 版本 |
| `init_factor_db.installed_version(con, "warehouse")` | 显式 | 依赖检查用 |

---

## 4. 数据契约（由因子管道保证，不在 init 模块实现）

### 4.1 复权口径：统一用后复权

`v_daily_qfq` 的基准是 `arg_max(adj_factor, trade_date)`（最新因子），历史值随新数据变化 → 回测不可复现。

`v_daily_hfq` 是 `price × adj_factor`，对历史稳定。

约定：

```sql
-- 推荐
SELECT * FROM v_daily_hfq;

-- 或显式
fact_daily.close * fact_adj_factor.adj_factor
```

**禁止用 `v_daily_qfq` 落因子值。**

### 4.2 单位归一化

`fact_daily` 直接继承 Tushare 定义：

- `vol` 单位是**手**（100 股）
- `amount` 单位是**千元**

因子管道入口必须统一转换：

```text
vol_shares  = vol * 100
amount_yuan = amount * 1000
```

不转换的后果：成交额类因子错 1000 倍；换手率类因子错 100 倍（`vol` 手 vs 股本 股）。这是最隐蔽的因子污染源，必须在管道单测或 `fact_factor_quality` 元数据里固化断言。

### 4.3 上游去重

自 warehouse v1.2.0 起，`fact_daily` / `fact_adj_factor` / `fact_daily_basic` /
`fact_stk_limit` 都有 `(ts_code, trade_date)` 主键，重复摄入会走 upsert 覆盖，
不会留下重复行。旧库（v1.1.0 及以前）没有主键，升级前必须先迁移/重建；
从外部 CSV/Parquet 导入时仍应在入库前去重。

管道强制步骤：

```sql
SELECT * FROM (
  SELECT *,
         row_number() OVER (PARTITION BY ts_code, trade_date) AS rn
  FROM fact_daily
) WHERE rn = 1;
```

建议在 `fact_factor_quality` 记录每张上游表的重复行数，`> 0` 时告警但不阻断（可能正在补数据）。

### 4.4 幸存者偏差：用日期判断，不用 `list_status`

`dim_stock_basic.list_status` 是**当前**快照；`WHERE list_status = 'L'` 会在历史回测中剔除已退市股票。

```sql
in_universe = (trade_date >= list_date)
          AND (delist_date IS NULL OR trade_date < delist_date)
```

### 4.5 `pre_close` 交叉校验

`fact_stk_limit.pre_close` 与 `fact_daily.pre_close` 理论应一致。管道可做廉价断言：

```sql
abs(a.pre_close - b.pre_close) > 0.005  -- 计入 n_outlier
```

用于发现涨跌停价口径漂移。

### 4.6 `formula_hash` 比对

写入 `fact_factor_daily` 前，比对编译期常量 `formula_hash` 与 `meta_factor_registry.formula_hash`：

- 一致 → 正常写入
- 不一致 → 拒绝写入，要求新开 `factor_id` 并把旧 ID 置 `is_active = FALSE`

---

## 5. 写入契约与幂等

| 表 | 写入方式 | 幂等键 | 重建方式 |
| --- | --- | --- | --- |
| `meta_factor_registry` | `INSERT ... ON CONFLICT (factor_id) DO UPDATE` | `factor_id` | 代码常量 + upsert |
| `fact_factor_daily` | `DELETE (factor_id, date_range)` → `INSERT` | `(factor_id, [start, end])` | 从 warehouse 区间重算 |
| `fact_tradable_flag` | `DELETE (date_range)` → `INSERT` | `[start, end]` | 从行情 + 涨跌停重建 |
| `fact_factor_quality` | `DELETE (factor_id, date_range)` → `INSERT` | 同上 | 随因子表重建 |
| `v_factor_*` | `CREATE OR REPLACE VIEW` | — | `init` / `refresh` |

每次区间重建在 `meta_ingest_log` 写一行：

```text
table_name = 'fact_factor_daily'
scope_key  = 'fid:{factor_id}:{start}:{end}'
status     = 'success' / 'failed'
row_count  = 写入行数
```

**禁止无条件 `TRUNCATE`**，否则并发只读会看到空窗。

---

## 6. 性能与容量

| 项 | 数值 / 决策 |
| --- | --- |
| 单年行数 | 5000 标的 × 250 日 × 200 因子 ≈ 2.5 亿 |
| 单年裸数据 | ~26 B/行 × 2.5 亿 ≈ 6.5 GB |
| 压缩后 | 约 1–2 GB/年 |
| 5 年全量 | 约 5–10 GB，单文件可承载 |
| 超过 ~50 GB | 建议拆分 factor 文件或归档 Parquet |
| 归档 | 超过 2 年按年导出 `factor/daily/year=YYYY/data.parquet`，`read_parquet(..., hive_partitioning=true)` 透明联合 |
| 分区键 | 按 year，不按 `ts_code`（高基数 → 小文件爆炸） |
| 索引 | 不加二级索引；因子消费以区间扫描为主，索引只加速点查 |
| 内存 | `threads=6` / `memory_limit=6GB`；大区间重算临时调大并配置 `temp_directory` 落盘 |
| 写入序 | `ORDER BY trade_date, ts_code`，或按日分批写入 |

`v_factor_wide` 单年约 125 万行 × (2 + 200) 列；PIVOT 聚合峰值内存可能接近值数据规模（~2 GB）加哈希表开销。带日期过滤查询，或把核心因子物化。

`table_row_counts` 用精确 `count(*)`，对 2.5 亿行的表是全表扫描——CLI 在超大库上会慢，这是精确语义的代价。

---

## 7. 实现要点

### 7.1 共享表零漂移

factor 不复制 DDL：

```python
SHARED_TABLES = tuple(
    t for t in init_market_db.TABLES
    if t.name in ("meta_schema_version", "meta_ingest_log")
)
TABLES = SHARED_TABLES + FACTOR_TABLES
```

market 改共享表，factor 自动跟随；实际库的结构漂移由 `verify_schema` 拦截。模块导入时若 `SHARED_TABLES` 不完整，直接 `RuntimeError`——fail-fast，不让 factor 在错误前提上初始化。

### 7.2 依赖检查（`_require_warehouse`）

1. `meta_schema_version` 是否存在；
2. `component = 'warehouse'` 行是否存在；
3. 版本是否 `>= 1.1.0`；
4. 必需行情表是否齐全。

任一失败都在**建表前**抛 `SchemaError`，事务回滚，库内不留任何 factor 对象。

### 7.3 初始化顺序

```text
BEGIN
  _require_warehouse()
  CREATE TABLE IF NOT EXISTS (共享 2 张 + factor 4 张)
  verify_schema(verify_views=False)
  CREATE OR REPLACE VIEW (v_factor_wide, v_factor_valid)
  _verify_views()
  INSERT factor 版本 ON CONFLICT DO UPDATE
COMMIT
```

`verify_schema` 提前到建视图前：残缺表以 `SchemaError` 暴露，而不是视图绑定时的 `BinderException`（后者错误信息不含表名，排查成本高）。

### 7.4 版本写入

```sql
INSERT INTO meta_schema_version (component, version)
VALUES (?, ?)
ON CONFLICT (component) DO UPDATE SET
  version = excluded.version,
  applied_at = now();
```

用 `now()` 而非 `current_timestamp`：后者在 `ON CONFLICT DO UPDATE SET` 上下文里会被 DuckDB 解析为列引用并报 `BinderException`。

### 7.5 动态宽表与刷新

`_create_wide_view` 流程：

1. 无活跃因子 → 两列简单视图；
2. 有活跃因子 → `PIVOT ... ON factor_id IN (...)`；
3. 失败或列数不符 → 条件聚合回退。

因子目录变更后：

```bash
python scripts/init_factor_db.py refresh --db "${MARKET_DB_PATH}"
```

---

## 8. 测试

```bash
pytest -q scripts/test_init_market_db.py scripts/test_init_factor_db.py
```

| 类别 | 用例 |
| --- | --- |
| 建表 / 视图 | `test_init_creates_factor_tables_and_views` |
| 幂等 / 版本 | `test_init_is_idempotent_and_versions_isolated`、`test_init_does_not_duplicate_version_rows`（market） |
| 共享表一致 | `test_shared_tables_use_exact_market_definitions` |
| 结构漂移 | `test_verify_detects_missing_factor_table`、`test_verify_detects_extra_column`、`test_verify_detects_type_drift`、`test_verify_detects_missing_view` |
| 版本隔离 | `test_market_init_after_factor_keeps_both_versions`、`test_installed_version_none_when_row_absent`（market） |
| 前置依赖 | `test_init_requires_warehouse`、`test_warehouse_version_too_old` |
| 幂等重建 | `test_range_rebuild_is_idempotent` |
| 可交易性 | `test_tradable_flag_filters_valid_view` |
| 宽表 | `test_wide_view_empty_registry_has_two_columns`、`test_wide_view_refresh_reflects_active_factors` |
| 资源 | `test_read_only_readers_coexist`、`test_same_process_rw_connections_share_instance` |
| 大输入 | `test_bulk_insert_10k_rows` |
| CLI | `test_cli_exit_codes`（0/1/2 + refresh） |

### 8.1 冒烟

```bash
python scripts/init_market_db.py init    --db "${MARKET_DB_PATH}"
python scripts/init_factor_db.py init    --db "${MARKET_DB_PATH}"
python scripts/init_factor_db.py check   --db "${MARKET_DB_PATH}"
python scripts/init_factor_db.py refresh --db "${MARKET_DB_PATH}"
```

### 8.2 SQL 验证

```sql
SELECT component, version FROM meta_schema_version ORDER BY component;
-- factor    1.2.0
-- warehouse 1.3.0

DESCRIBE v_factor_wide;
DESCRIBE v_factor_valid;

EXPLAIN ANALYZE
SELECT * FROM v_factor_valid
WHERE trade_date >= DATE '2024-01-01' AND trade_date < DATE '2025-01-01';
```

### 8.3 场景覆盖

| 场景 | 覆盖用例 |
| --- | --- |
| 正常路径 | 建表/建视图、版本隔离、共享表一致、market 向后兼容 |
| 边界值 | 空因子目录宽表 2 列；活跃/停用混合；停牌行被剔除 |
| 异常路径 | 空库 init、warehouse 版本过低、缺表、缺列、类型漂移、缺视图、非法 component |
| 并发 | 同进程 RW 共享实例；多只读读者并存 |
| 大输入 | 10k 行 `executemany` |
| 幂等 | 三连 init；区间 DELETE+INSERT 行数不增 |

---

## 9. 对 market 模块的改动

`init_market_db.py` 仅 4 处改动：

1. 新增 `WAREHOUSE_COMPONENT`、`_COMPONENT_RE`、`_validate_component()`；
2. `init_schema` 的版本 upsert 改为参数绑定 `[WAREHOUSE_COMPONENT, SCHEMA_VERSION]`；
3. `installed_version(con, component="warehouse")` 增加参数，默认值保持向后兼容；
4. CLI 日志打印 `component=warehouse`。

`verify_schema` / `table_row_counts` / `connect` 完全不变：factor 表是额外对象，market 的严格校验只看自己的 `TABLES`，不会因为库里多了 factor 表而失败。

---

## 10. 复杂度与资源

| 操作 | 时间 | 空间 | I/O / 说明 |
| --- | --- | --- | --- |
| `init_schema` | O(T + F + C) = O(6 + F + 60) | O(F) 字符串 | 6 张 `CREATE TABLE IF NOT EXISTS` + 2 个视图 + 1 次版本 upsert；F 通常 ≤ 200 |
| `verify_schema` | O(C + F) | O(C) | 一次 `duckdb_columns()` 全量元数据 + 2 次 `DESCRIBE` |
| `refresh_views` | O(F) + 2 DDL | O(F) | 仅重建视图，不动数据 |
| `table_row_counts` | O(N) | O(T) | `count(*)` 对 `fact_factor_daily` 是全表扫描 |
| `v_factor_valid` 查询 | O(N + M) | O(min(N,M)) | JOIN 哈希表；`trade_date` 过滤可触发 zone map 剪枝 |
| `v_factor_wide` 查询 | O(N) 扫描 + O(G·F) 聚合 | O(G·F) 峰值 | G ≈ 125 万/年，F = 200 时峰值 ~2 GB 量级，需日期过滤或物化 |

**容量**：单年 2.5 亿行 → 裸 6.5 GB → 压缩 1–2 GB；5 年 5–10 GB，单文件可承载；> 50 GB 拆分。

---

## 11. 泄漏与安全检查表

### 11.1 内存 / 资源泄漏

| 检查项 | 状态 |
| --- | --- |
| 连接生命周期 | 已满足：复用 market `database()`，`finally` 关闭；`init_schema` / `refresh_views` 不关闭调用方连接 |
| 事务 | 已满足：显式 `BEGIN / COMMIT / ROLLBACK`，异常不留半成品 |
| 句柄 | 已满足：`connect()` 构造失败时 `con.close()` 后 re-raise |
| 游标 | 已满足：`fetchone` / `fetchall` 即取即弃 |
| 线程/协程 | 不涉及：无自建线程池、无未 await 的 Task |
| 缓存 | 不涉及：无无界 dict 缓存，`TABLES` 等均为模块级不可变常量 |
| 大对象 | 已满足：动态 SQL 仅 O(F) 字符串，无闭包持有 DataFrame |
| 视图替换 | 已满足：`CREATE OR REPLACE`，失败随事务回滚恢复旧定义 |
| 临时目录 | 已满足：继承 market，`mkdir(mode=0700)` |
| 循环引用 | 不涉及：无 `__del__` |

**需调用方保证**：

- 因子管道自己管理批次连接，不跨请求复用 RW 连接；
- 不在已开启事务中调用 `refresh_views`（会二次 `BEGIN`）；
- 并发写入串行化（DuckDB 跨进程单写者）；
- 上游去重、单位归一化、`formula_hash` 比对由管道负责。

### 11.2 信息安全泄露

| 检查项 | 状态 |
| --- | --- |
| 硬编码密钥 | 已满足：无 token / DSN / 证书 |
| SQL 注入 | 已满足：`component` 参数绑定 + 正则白名单；动态 SQL 只拼 `int(factor_id)`；表名/视图名来自模块常量 |
| 日志脱敏 | 已满足：只打印表名、行数、版本号；不打印因子值、股票列表、token |
| 异常回显 | 已满足：CLI 只输出业务错误码；`duckdb.Error` 进日志，不回显堆栈给外部调用方 |
| 文件权限 | 已满足：继承 0600/0700 |
| 只读保护 | 已满足：`read_only=True` 不写、不 chmod |
| 外部命令 | 已满足：无 `shell=True`、无 `eval/exec/pickle` |
| 依赖 | 仅 `duckdb`；上线前锁版本 + CVE 扫描 |

**需调用方保证**：`meta_factor_registry.description` 不写内网地址/密钥/隐私；对外 API 不要透传 `duckdb.Error` 原始消息。

---

## 12. 权衡与可演进

1. **动态 PIVOT 视图需手动 `refresh`**：因子目录高频增删时容易忘记刷新。若每日增删，建议把 `refresh_views` 挂到目录 upsert 之后自动执行，或改物化核心因子表。
2. **`v_factor_valid` 的「或」语义**：保留涨停股是正确但反直觉的，必须在团队内统一口径，否则不同策略对同一视图的理解会分歧。若分歧大，可再拆 `v_factor_buyable` / `v_factor_sellable` 两个视图。
3. **同库单写者**：所有 factor 批次写入串行。阈值：单库 P95 写入等待 > 5 分钟，或文件 > 50 GB，就拆独立 `factor.duckdb` + `ATTACH`。
4. **`table_row_counts` 精确计数**：2.5 亿行/年时是全表扫描。状态展示可改 `duckdb_tables().estimated_size`，但 API 语义要从「精确」改成「估算」，需显式改名。
5. **ST 日频快照缺失**：`is_st` 只能置 `FALSE`。要真正复现 ST 剔除类因子，必须在 warehouse 新增 `fact_stock_status`，这是比 factor schema 更上游的缺口。
6. **上游去重**：v1.2.0 起主键已能防止重复行；仍需保留入库前去重，处理旧库迁移与外部文件导入。
7. **DuckDB 不是多写者数据库**：未来多团队并发写因子时，迁 ClickHouse / PostgreSQL / 专用特征库；DuckDB 保留为研究快照与 Parquet 归档格式。

**若假设不成立需如何调整**：若 DuckDB 版本不支持 `PIVOT ... USING FIRST` 或视图内 `ORDER BY`，会自动走条件聚合回退（已实现，测试覆盖 `test_wide_view_refresh_reflects_active_factors`），无需改代码；若必须独立 `factor.duckdb`，则 `v_factor_valid` 需改为跨库 `ATTACH` 引用，`_require_warehouse` 也要改成检查 ATTACH 别名而非同库表名——这一改动会连带影响 `verify_schema` 与全部测试夹具，属于独立方案，建议单开一版。

---

## Appendix: Edition History

| 版本 | 变更 |
| --- | --- |
| `1.2.0` | `v_factor_valid` 增加 `is_stale = FALSE`；新增 `build_tradable_flags.py` 派生 `fact_tradable_flag`；明确 `is_st` 当前不伪造历史 |
| `1.1.0` | 初版：4 张 factor 表 + 2 个视图；共享 market 表定义；动态 PIVOT 宽表 + 条件聚合回退；warehouse 版本依赖检查；`installed_version` 组件隔离；`refresh` 子命令；明确 `v_factor_valid` 的「或」语义边界 |

---

END OF FILE
