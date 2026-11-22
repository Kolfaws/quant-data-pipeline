# Quant Data Pipeline

负责 PostgreSQL 日频行情发布，以及现有研究库 `market.duckdb` 的建表、行情摄入与因子层结构。DuckDB 路径由 `${MARKET_DB_PATH}` 指定。

```text
market.duckdb
├── warehouse 组件（component='warehouse'，v1.3.0）  基础行情
└── factor    组件（component='factor'，v1.2.0）     因子层
```

> **表结构不在本仓库硬编码**：DDL 来自 `quant_schema.market_ddl`；
> 本项目的 `init_market_db.py` / `init_factor_db.py` 只负责事务、校验与版本行。

## 1. 职责边界

| 项目 | 负责的库/表 | 权限 |
| --- | --- | --- |
| **quant-data-pipeline** | `market.duckdb`：warehouse + factor 表结构；写入基础行情 | RW |
| quant-baseline | 只读 `market.duckdb`；写 `backtest.duckdb` 的基准表 | market RO |
| quant-backtest-engine | 建 `backtest.duckdb`；写净值 | market RO |
| quant-factor | 写 `market.duckdb` 的 factor 组件 | market RW |

- 行情管道管理 PostgreSQL 行情结构与 `market.duckdb`，回测表由 backtest engine 管理。
- **单写多读**：DuckDB 写入以文件为单位加锁；quant-factor 与 backtest 同时运行时，
  backtest 必须以 `read_only=True` 打开。
- 因子值写入由 quant-factor 负责；本项目只初始化 factor 表结构。

## 2. 目录结构

```text
quant-data-pipeline/
├── data/                       # 本地中转目录（可选）
├── docs/
│   ├── README.md                # 按需阅读索引
│   ├── init_market_db.md       # warehouse 表结构、版本、API
│   ├── init_factor_db.md       # factor 表结构、宽表视图
│   ├── ingest_market_data.md   # Tushare 摄入与降级策略
│   └── tushare_refer/          # Tushare 接口字典（按类别分目录）
├── scripts/
│   ├── init_market_db.py       # warehouse 建表/校验（DDL 来自 quant_schema）
│   ├── init_factor_db.py       # factor 建表/视图/refresh
│   ├── ingest_market_data.py   # Tushare -> market.duckdb（幂等）
│   ├── import_refer_docs.py    # refer.txt -> docs/tushare_refer/*.md
│   ├── build_tradable_flags.py # 派生 fact_tradable_flag
│   ├── seed_index_demo.py      # 无 index_daily 权限时的演示补数
│   ├── test_init_market_db.py
│   ├── test_init_factor_db.py
│   ├── test_ingest_market_data.py
│   ├── test_build_tradable_flags.py
│   ├── test_write_guards.py    # 显式路径 / test env / 2010 写入闸门
│   └── test_market_views.py
├── src/data_pipeline/
│   ├── config.py               # .env 读取（无 dotenv 依赖）
│   ├── db.py                   # 统一 DuckDB 连接器（被其他项目复用）
│   ├── guards.py               # 显式库路径 / 2010 写入闸门
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
MARKET_DB_PATH=/absolute/path/to/market.duckdb
MARKET_TEST_DB_PATH=/absolute/path/to/market_test.duckdb
LOG_LEVEL=INFO
```

- 真实环境变量优先于 `.env`；`.env` 已被 gitignore，禁止提交。
- `.env` 由 `src/data_pipeline/config.py` 直接解析，不依赖 `python-dotenv`。
- 代码中不写死任何绝对路径或 Token。
- **库路径必须显式**：`--db` 或环境变量；脚本不再回退 `data/market.duckdb`
  这类相对默认路径。旧变量名 `DUCKDB_PATH` / `DUCKDB_TEST_PATH` 仍作为兼容别名读取。
- `--env test` 只读 `MARKET_TEST_DB_PATH`；未配置时立即失败（退出码 2），
  不会回退正式库。

## 5. 初始化

```bash
# 1) warehouse（必须先执行；--db 或 MARKET_DB_PATH 必须显式）
uv run python scripts/init_market_db.py init --db "${MARKET_DB_PATH}"

# 2) factor（会检查 warehouse 版本 >= 1.1.0）
uv run python scripts/init_factor_db.py init --db "${MARKET_DB_PATH}"

# 3) 校验；因子目录变更后刷新宽表视图
uv run python scripts/init_factor_db.py check --db "${MARKET_DB_PATH}"
uv run python scripts/init_factor_db.py refresh --db "${MARKET_DB_PATH}"
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

# 也可以用 --env test 指定现有初始化命令（需配置 MARKET_TEST_DB_PATH）
uv run python scripts/init_market_db.py init --env test
uv run python scripts/init_factor_db.py init --env test
```

因子正式发布入口待实现，设计与验收见 [QuantData 存储与研究架构](../docs/quantdata-postgresql-duckdb-design.md)。
测试回测库由 [`init_test_db.py`](../quant-backtest-engine/scripts/init_test_db.py) 初始化。

## 6. 摄入行情

```bash
# 当前研究库只保留 2010；脚本默认区间就是 2010-01-01..2010-12-31
# 范围：交易日历 + 股票列表 + 样本股（日线/复权/核心票 daily_basic/涨跌停）+ 3 个指数 + 3 只宽基 ETF
uv run python scripts/ingest_market_data.py \
    --db "${MARKET_DB_PATH}" \
    --start 2010-01-01 --end 2010-12-31

# 只补指定股票（区间仍取默认 2010）
uv run python scripts/ingest_market_data.py --stocks 600519.SH,000858.SZ

# 派生每日可交易标记（依赖 fact_daily + fact_stk_limit）
uv run python scripts/build_tradable_flags.py \
    --db "${MARKET_DB_PATH}" --start 2010-01-01 --end 2010-12-31 --apply

# 额外抓指数成分权重（需要 Tushare index_weight 权限）
uv run python scripts/ingest_market_data.py --with-index-weight

# 没有 index_daily 权限时，可用公开 K 线补指数（仅演示/应急）
uv run python scripts/seed_index_demo.py --db "${MARKET_DB_PATH}"
```

**2010 写入闸门**：`ingest_market_data.py` / `build_tradable_flags.py` /
`seed_index_demo.py` 的默认区间是 2010；目标为 `MARKET_DB_PATH` 且
`end > 2010-12-31` 时 fail-fast（退出码 2，不写库）。写 2011+ 只能用新库/新版本：

```bash
# --allow-post-2010 只对新库/新版本生效，不能解锁当前研究库
uv run python scripts/ingest_market_data.py \
    --db "${MARKET_TEST_DB_PATH}" \
    --start 2011-01-01 --end 2011-12-31 --allow-post-2010
```

写入策略：

- **整批一个事务**：行情写入与 `meta_ingest_log` 同一事务提交；
  `duckdb.Error` / 中断会整批回滚，并在回滚后补写一条 failed 批次日志，
  不会出现“部分表已写、无记录”；
- 每张表 `INSERT ... ON CONFLICT (主键) DO UPDATE`，重复执行行数不膨胀；
- 限频/权限错误（`FetchError`）记 failed 日志后跳过，不阻断其他标的；
- 每条 `meta_ingest_log.detail` 带 `batch_id=<uuid>`；另有一行
  `table_name='ingest_batch'` 的批次汇总（ok/failed + 错误摘要）；
- 交易日历接口不可用时，自动从 `fact_daily` 的交易日反推 `dim_trade_cal`。

详细说明见 [docs/ingest_market_data.md](docs/ingest_market_data.md)。

## 7. 表结构

warehouse（11 张表 + 3 视图 + 1 表宏）：

| 表 | 主键 | 说明 |
| --- | --- | --- |
| `meta_schema_version` | `component` | warehouse / factor 各一行 |
| `meta_ingest_log` | `(table_name, scope_key)` | 摄入批次；`detail` 含 `batch_id`/错误，`ingest_batch` 行为批次汇总 |
| `dim_stock_basic` | `ts_code` | 股票基础信息 |
| `dim_trade_cal` | `(exchange, cal_date)` | 交易日历 |
| `fact_daily` | `(ts_code, trade_date)` | 个股日线 |
| `fact_adj_factor` | `(ts_code, trade_date)` | 复权因子 |
| `fact_daily_basic` | `(ts_code, trade_date)` | 市值/换手/估值 |
| `fact_stk_limit` | `(ts_code, trade_date)` | 涨跌停价 |
| `fact_index_daily` | `(index_code, trade_date)` | 指数日线（v1.2.0 新增） |
| `fact_index_weight` | `(index_code, trade_date, con_code)` | 指数成分权重（v1.2.0 新增） |
| `fact_fund_daily` | `(ts_code, trade_date)` | ETF/基金日线（v1.2.0 新增） |

视图：`v_daily_qfq`、`v_daily_hfq`、`v_daily_return`；表宏：`qfq_daily(as_of)`。

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

- [docs/README.md](docs/README.md)（按需阅读索引）
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
uv run --with pytest pytest scripts/test_write_guards.py -q   # 2010 闸门 / test env / 显式路径
```

Windows 下 POSIX 权限相关用例会自动跳过。

## 9. 版本历史

| 版本 | 变更 |
| --- | --- |
| `1.1.0` | warehouse 初始结构（8 表 + 2 视图） |
| `1.3.0` | 新增 `qfq_daily(as_of)` 表宏、`v_daily_return` 视图；qfq/hfq 的 `vol` 与价格反向调整、`amount` 保持真实成交额 |
| `1.2.0` | 新增 `fact_index_daily` / `fact_index_weight` / `fact_fund_daily`；为存量表补主键 |
| factor `1.2.0` | `v_factor_valid` 增加 `is_stale = FALSE`；新增 `build_tradable_flags.py` |
| factor `1.1.0` | 因子目录/因子值/可交易标记/质量/验证/发布 + 宽表视图 |

## 10. PostgreSQL 日频首批

安装 `uv sync --extra postgres`，按 `.env.example` 配置 `POSTGRE_IP`、`POSTGRE_DB`、
管理员、writer、reader 和 `TUSHARE_TOKEN`。初始化用管理员，摄入用 writer，查询和导出用
reader。单一 DSN 环境可以设置 `QUANTDATA_POSTGRES_DSN` 并自行管理权限。
`--env-file` 选择项目配置，可通过 `QUANTDATA_POSTGRES_ENV` 引用共享 `.env`。
进程环境优先，其次是显式文件，再其次是被引用的文件。

```powershell
uv run --extra postgres python scripts/market_postgres.py init
uv run --extra postgres python scripts/market_postgres.py check
uv run --extra postgres python scripts/market_postgres.py ingest --start 2010-01-04 --end 2010-01-08
uv run --extra postgres python scripts/market_postgres.py export --start 2010-01-04 --end 2010-01-08 --version 1 --output research-input-2010
```

每批接收最多 31 个自然日。当前来源覆盖上交所、深交所的交易日历、股票基础资料与
上市/退市日期、未复权日线和对应复权因子，价格及量额沿用 Tushare 日线单位。
停牌与供应商个股漏采尚无独立来源对账。若日线含供应商当前档案中缺失的历史代码，保留
其行情并在导出清单列出这些代码，上市及退市日期继续留空。
导出按发布版本和日期生成 Parquet 与校验清单，可用 `--code` 限定标的，DuckDB 可直接
用 `read_parquet` 读取。历史回填记录实际采集时间，股票现状和复权历史不保证严格 PIT。

正式因子表已定义。因子发布工作流、受审修订和 L0 原始响应归档属于后续接入范围。

## 11. PostgreSQL 回测净值

回测引擎在 DuckDB 计算并保存成功 run。通过管道发布净值时，明确选择 DuckDB 文件、
run ID 和用于该次回测的行情发布版本。发布时校验版本覆盖净值日期。相同净值和表内元数据重跑
返回已有修订，内容变化生成新修订。完整策略配置和其他指标由原 DuckDB run 保存。
reader 按 run ID 和修订号回读，CSV 可供 DuckDB 或看板使用。

```powershell
uv run --extra postgres python scripts/market_postgres.py init-nav
uv run --extra postgres python scripts/market_postgres.py publish-nav --duckdb path/to/backtest.duckdb --run-id example --input-version 1
uv run --extra postgres python scripts/market_postgres.py export-nav --run-id example --revision 1 --output nav.csv
```
