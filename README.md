# Quant Data Pipeline

统一数据底座的**唯一写入方**：负责 `market.duckdb`（路径由 `${MARKET_DB_PATH}` 指定）的建表、行情摄入与因子层结构。

```text
market.duckdb
├── warehouse 组件（component='warehouse'，v1.2.0）  基础行情
└── factor    组件（component='factor'，v1.1.0）     因子层
```

> **表结构不在本仓库硬编码**：DDL 来自 `quant_schema.market_ddl`；
> 本项目的 `init_market_db.py` / `init_factor_db.py` 只负责事务、校验与版本行。

## 1. 职责边界

| 项目 | 负责的库/表 | 权限 |
| --- | --- | --- |
| **quant-data-pipeline** | `market.duckdb`：warehouse + factor 表结构；写入基础行情 | RW |
| quant-baseline | 只读 `market.duckdb`；写 `backtest.duckdb` 的基准表 | market RO |
| quant-backtest-engine | 建 `backtest.duckdb`；写净值 | market RO |
| factor-research | 写 `market.duckdb` 的 factor 组件 | market RW |

- **保持本项目纯净**：只碰 `market.duckdb`，不建 `backtest.duckdb` 的表。
- **单写多读**：DuckDB 写入以文件为单位加锁；factor_research 与 backtest 同时运行时，
  backtest 必须以 `read_only=True` 打开。
- 因子写入采用 `DELETE + INSERT` 的增量方式，不做整库重建。

## 2. 目录结构

```text
quant-data-pipeline/
├── data/                       # 本地中转目录（可选）
├── docs/
│   ├── init_market_db.md       # warehouse 表结构、版本、API
│   ├── init_factor_db.md       # factor 表结构、宽表视图
│   └── ingest_market_data.md   # Tushare 摄入与降级策略
├── scripts/
│   ├── init_market_db.py       # warehouse 建表/校验（DDL 来自 quant_schema）
│   ├── init_factor_db.py       # factor 建表/视图/refresh
│   ├── ingest_market_data.py   # Tushare -> market.duckdb（幂等）
│   ├── seed_index_demo.py      # 无 index_daily 权限时的演示补数
│   ├── test_init_market_db.py
│   └── test_init_factor_db.py
├── src/data_pipeline/
│   ├── config.py               # .env 读取（无 dotenv 依赖）
│   ├── db.py                   # 统一 DuckDB 连接器（被其他项目复用）
│   ├── logger.py
│   ├── core/errors.py
│   └── sources/tushare_src.py  # Tushare -> polars
├── Makefile
├── pyproject.toml
└── README.md
```

## 3. 安装

```bash
# 只装必要的库
uv add --editable ../quant-db-schema
uv add duckdb polars pyarrow pytz tushare
uv sync
```

> `quant-db-schema` 的 Python 包名是 `quant_schema`（代码里 `from quant_schema...`）。
> `pyarrow` 是 DuckDB `register(polars_df)` 的运行时依赖；`pytz` 用于读取
> `TIMESTAMPTZ` 列。两者都不能省。

本项目采用 `src/` 布局，`uv sync` 会以 editable 方式安装 `data_pipeline`；
测试路径由 `pyproject.toml` 的 `pythonpath = ["src", "scripts"]` 提供，
脚本和测试中不再使用 `sys.path.insert`。

要求 Python >= 3.13。

> 当前可用入口是 `scripts/init_market_db.py`、`scripts/init_factor_db.py`、
> `scripts/ingest_market_data.py`。`src/data_pipeline/cli.py` 与通用
> Source/Cleaner/Sink 骨架仍待完善；日常数据接入请直接用上面的脚本。

## 4. 配置

复制 `.env.example` 为 `.env`：

```env
TUSHARE_TOKEN=
DUCKDB_PATH=/absolute/path/to/market.duckdb
LOG_LEVEL=INFO
```

- 真实环境变量优先于 `.env`；`.env` 已被 gitignore，禁止提交。
- `.env` 由 `src/data_pipeline/config.py` 直接解析，不依赖 `python-dotenv`。
- 代码中不写死任何绝对路径或 Token。

## 5. 初始化

```bash
# 1) warehouse（必须先执行）
uv run python scripts/init_market_db.py init

# 2) factor（会检查 warehouse 版本 >= 1.1.0）
uv run python scripts/init_factor_db.py init

# 3) 校验；因子目录变更后刷新宽表视图
uv run python scripts/init_factor_db.py check
uv run python scripts/init_factor_db.py refresh
```

两个脚本必须指向同一个库文件，并按 `warehouse → factor` 顺序执行。
初始化期间不要并发写入（DuckDB 跨进程单写者）。

### 测试库

正式库和测试库共用 DDL，但文件独立：

```bash
# 初始化 market_test.duckdb（warehouse + factor）
uv run python scripts/init_test_dbs.py

# 从正式库复制 warehouse 行情，供因子/基准实验
uv run python scripts/sync_test_market.py --apply

# 也可以用 --env test 指定现有初始化命令
uv run python scripts/init_market_db.py init --env test
uv run python scripts/init_factor_db.py init --env test
```

测试因子通过 `quant-factor` 的 `promote_test_factor.py` 发布到正式库；
测试 backtest 库由 `quant-backtest-engine/scripts/init_test_db.py` 初始化。

## 6. 摄入行情

```bash
# 默认：交易日历 + 股票列表 + 20 只样本股（日线/复权/核心票 daily_basic）+ 3 个指数
uv run python scripts/ingest_market_data.py \
    --db "${MARKET_DB_PATH}" \
    --start 2015-01-01 --end 2026-11-06

# 只补指定股票
uv run python scripts/ingest_market_data.py --stocks 600519.SH,000858.SZ

# 额外抓指数成分权重（需要 Tushare index_weight 权限）
uv run python scripts/ingest_market_data.py --with-index-weight

# 没有 index_daily 权限时，可用公开 K 线补指数（仅演示/应急）
uv run python scripts/seed_index_demo.py
```

写入策略：

- 每张表 `INSERT ... ON CONFLICT (主键) DO UPDATE`，重复执行行数不膨胀；
- 每张表的批次写入结果记入 `meta_ingest_log`；
- 限频/权限错误会记录 warning 并跳过，不阻断其他标的；
- 交易日历接口不可用时，自动从 `fact_daily` 的交易日反推 `dim_trade_cal`。

详细说明见 [docs/ingest_market_data.md](docs/ingest_market_data.md)。

## 7. 表结构

warehouse（11 张表 + 2 视图）：

| 表 | 主键 | 说明 |
| --- | --- | --- |
| `meta_schema_version` | `component` | warehouse / factor 各一行 |
| `meta_ingest_log` | `(table_name, scope_key)` | 摄入批次 |
| `dim_stock_basic` | `ts_code` | 股票基础信息 |
| `dim_trade_cal` | `(exchange, cal_date)` | 交易日历 |
| `fact_daily` | `(ts_code, trade_date)` | 个股日线 |
| `fact_adj_factor` | `(ts_code, trade_date)` | 复权因子 |
| `fact_daily_basic` | `(ts_code, trade_date)` | 市值/换手/估值 |
| `fact_stk_limit` | `(ts_code, trade_date)` | 涨跌停价 |
| `fact_index_daily` | `(index_code, trade_date)` | 指数日线（v1.2.0 新增） |
| `fact_index_weight` | `(index_code, trade_date, con_code)` | 指数成分权重（v1.2.0 新增） |
| `fact_fund_daily` | `(ts_code, trade_date)` | ETF/基金日线（v1.2.0 新增） |

视图：`v_daily_qfq`、`v_daily_hfq`。

factor（7 张表 + 2 视图）：

| 表 | 主键 |
| --- | --- |
| `meta_factor_registry` | `factor_id` |
| `fact_factor_daily` | `(ts_code, trade_date, factor_id)` |
| `fact_tradable_flag` | `(ts_code, trade_date)` |
| `fact_factor_quality` | `(factor_id, trade_date)` |
| `meta_factor_profile` | `factor_id` |
| `meta_factor_validation` | `(factor_id, env, validated_at)` |
| `meta_factor_promotion_log` | `promotion_id` |

视图：`v_factor_valid`、`v_factor_wide`（列由活跃因子动态生成）。

字段级说明：

- [docs/init_market_db.md](docs/init_market_db.md)
- [docs/init_factor_db.md](docs/init_factor_db.md)

## 8. 开发与测试

```bash
make install
make test          # scripts/ 下的 pytest
make lint
make format
```

直接使用 pytest：

```bash
uv run --with pytest pytest scripts/test_init_market_db.py scripts/test_init_factor_db.py -q
```

Windows 下 POSIX 权限相关用例会自动跳过。

## 9. 版本历史

| 版本 | 变更 |
| --- | --- |
| `1.1.0` | warehouse 初始结构（8 表 + 2 视图） |
| `1.2.0` | 新增 `fact_index_daily` / `fact_index_weight` / `fact_fund_daily`；为存量表补主键 |
| factor `1.1.0` | 因子目录/因子值/可交易标记/质量/验证/发布 + 宽表视图 |
