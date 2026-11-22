# ingest_market_data — Tushare 行情摄入

`scripts/ingest_market_data.py` 负责把 Tushare 数据写入
`${MARKET_DB_PATH}` 的 warehouse 组件。它是基准/回测/因子研究共同的数据入口。

## 1. 数据流

```text
Tushare pro_api
  ├── trade_cal       ─┐
  ├── stock_basic      │
  ├── daily            │    polars DataFrame
  ├── adj_factor       ├──> data_pipeline.sources.tushare_src
  ├── daily_basic      │    （列名对齐 quant_schema.market_ddl）
  ├── stk_limit        │
  ├── index_daily      │
  ├── fund_daily       │
  └── index_weight    ─┘
                              │
                              ▼
                 upsert + meta_ingest_log
                              │
                              ▼
                  market.duckdb（warehouse）
```

## 2. 命令

脚本默认区间是 `2010-01-01..2010-12-31`（当前研究库只保留 2010）。
目标为 `MARKET_DB_PATH` 且 `end > 2010-12-31` 时脚本 fail-fast（退出码 2，不建库/不写库）；
写 2011+ 只允许新库/新版本，并显式加 `--allow-post-2010`。
`--db` 缺省时读 `MARKET_DB_PATH`；两者都没有则报错，不再回退相对路径默认库。

```bash
python scripts/ingest_market_data.py \
    --db "${MARKET_DB_PATH}" \
    --start 2010-01-01 --end 2010-12-31 \
    --stocks 600519.SH,000858.SZ,... \
    --indexes 000300.SH,000905.SH,000852.SH \
    --daily-basic core \
    --with-index-weight

# 新库/新版本写 2011+
python scripts/ingest_market_data.py --db "$MARKET_TEST_DB_PATH" \
    --start 2011-01-01 --end 2011-12-31 --allow-post-2010
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--db` | `MARKET_DB_PATH` | market.duckdb 路径；env 未配置则报错（无相对路径回退） |
| `--start` / `--end` | `2010-01-01` / `2010-12-31` | `YYYY-MM-DD`；越界受 2010 写入闸门约束 |
| `--allow-post-2010` | 关 | 仅新库/新版本允许 `end>2010-12-31`；不作用于 `MARKET_DB_PATH` |
| `--calendar` | `SSE` | 交易日历交易所 |
| `--stocks` | 20 只样本股 | 逗号分隔；传空跳过个股 |
| `--indexes` | `000300.SH,000905.SH,000852.SH` | 逗号分隔；传空跳过指数 |
| `--funds` | `510300.SH,510500.SH,159915.SZ` | 逗号分隔的 ETF；传空则跳过 |
| `--daily-basic` | `core` | `all` / `core`（前 5 只）/ `none` |
| `--stk-limit` | `all` | `all` / `core`（前 5 只）/ `none`；用于派生 `fact_tradable_flag` |
| `--with-index-weight` | 关 | 需要 Tushare 权限 |

## 3. 幂等与主键

> 股票池注意：`stock_basic` 默认只取 `list_status='L'`，`dim_stock_basic` 不含退市股；
> 默认 20 只样本股是当前大票，不是 2010 PIT 股票池。历史研究股票池需另行补退市/
> 成分数据，不能用当前名单回填历史。

| 表 | 幂等键 |
| --- | --- |
| `dim_trade_cal` | `(exchange, cal_date)` |
| `dim_stock_basic` | `ts_code` |
| `fact_daily` | `(ts_code, trade_date)` |
| `fact_adj_factor` | `(ts_code, trade_date)` |
| `fact_daily_basic` | `(ts_code, trade_date)` |
| `fact_stk_limit` | `(ts_code, trade_date)` |
| `fact_index_daily` | `(index_code, trade_date)` |
| `fact_index_weight` | `(index_code, trade_date, con_code)` |
| `fact_fund_daily` | `(ts_code, trade_date)` |

写入使用 `INSERT INTO ... BY NAME SELECT * FROM <registered frame> ON CONFLICT
(keys) DO UPDATE`，同一标的重复拉取只覆盖，不追加。

**事务语义**：整个摄入（所有表 + `meta_ingest_log`）包在一个事务里。

- 正常结束：数据与日志一起 `COMMIT`；
- 单表 `FetchError`（限频/无权限）：事务内记一条 failed 日志后继续，属于预期降级；
- `duckdb.Error`、`KeyboardInterrupt` 等：整批 `ROLLBACK`，然后单独写一条
  `ingest_batch` failed 日志（含 `batch_id` 与错误摘要），不会留下
  “部分表已写、无记录”的状态。

## 4. 限频与权限降级

Tushare 不同积分档位的接口频率差异很大。脚本按以下策略降级：

| 情况 | 行为 |
| --- | --- |
| `trade_cal` 被限频 | 记录 failed，后续从 `fact_daily` 的实际交易日反推 |
| `stock_basic` 被限频 | 记录 failed，不阻断日线 |
| `adj_factor` 被限频 | 跳过该标的复权因子；`fact_daily.pct_chg` 仍可用于收益 |
| `daily_basic` 被限频 | 跳过；市值加权基准需等该表补齐后再启用 |
| `stk_limit` 被限频/无权限 | 跳过；`build_tradable_flags.py` 的 `is_limit_up/down` 会退化为 `FALSE` 并告警 |
| `fund_daily` 无权限 | 记录 failed，ETF 基准保持 `enabled: false` |
| `index_weight` 无权限 | 首次失败即停止后续月份，动态标的池不可用 |

`TushareSource` 对“频/超限/权限/积分”类错误**不做指数退避重试**，避免继续消耗额度；
网络类错误仍会重试 3 次。

可交易标记不在 ingest 中派生，需在行情和涨跌停就绪后单独执行：

```bash
python scripts/build_tradable_flags.py --start 2010-01-01 --end 2010-12-31 --apply
```

## 5. 5000 积分 token 的推荐顺序

1. 先拉个股日线（`daily` 通常额度较高）：
   ```bash
   python scripts/ingest_market_data.py --indexes= --daily-basic none --stk-limit none
   ```
2. 5000 积分可补 `adj_factor` / `daily_basic`，并建议同时补 `stk_limit`：
   ```bash
   python scripts/ingest_market_data.py --stocks 600519.SH,... --indexes= --daily-basic all --stk-limit all
   ```
3. `index_daily` 有权限时单独补指数；没有权限可用
   `scripts/seed_index_demo.py` 拉公开 K 线，仅用于打通流程。
4. `index_weight` 有权限后再启用 `BI_EQW_HS300`。
5. 行情/涨跌停补完后运行 `build_tradable_flags.py`，再使用 `v_factor_valid`。

## 6. 调度建议

- 交易日收盘后（18:00 之后）执行一次；重复执行安全。
- 当前 2010 研究库的增量区间仍须落在 2010 内；`--start 2010-12-01 --end 2010-12-31`
  靠 upsert 覆盖修订。写 2011+ 必须换新库并加 `--allow-post-2010`。
- 大规模全市场回补建议按年份分段，避免单次请求/内存过大。

## 7. 元数据

每次表级写入都会 upsert `meta_ingest_log`：

| 字段 | 说明 |
| --- | --- |
| `table_name` | 目标表；批次汇总行的伪表名为 `ingest_batch` |
| `scope_key` | 范围键，如 `600519.SH:2010-01-01:2010-12-31`；汇总行为 `start:end` |
| `row_count` | 写入行数（汇总行为本批成功行数合计） |
| `status` | `ok` / `failed` |
| `detail` | `batch_id=<uuid>` 前缀 + 本表错误摘要；汇总行另含错误类型/信息 |
| `started_at` / `finished_at` | 起止时间 |

`batch_id` 是每次运行生成的 UUID（同一批所有表共用），用于把失败回滚后的
`ingest_batch` 记录与日志检索关联起来（schema 无独立列，存在 `detail` 里）。
同一 `(table_name, scope_key)` 重复执行会覆盖日志，不膨胀；回滚场景下只会留下
一条 `ingest_batch` failed 记录，其余表日志随事务回滚。

## 8. 常见问题

- **`ModuleNotFoundError: six`**：Tushare 依赖缺失，`uv add tushare` 应自动安装；手动环境可 `uv pip install six`。
- **`index_daily` 报权限**：不是代码问题，是 token 积分；用 `seed_index_demo.py` 或升级权限。
- **写入时报主键冲突**：说明 market 库是旧版本（没有主键）。本仓库默认新建；
  旧库需要迁移/重建后再用 upsert。
- **DuckDB 文件被占用**：同一文件只允许一个 RW 连接；确认没有另一个初始化/写入进程。

## 9. 接口参考

按 Tushare 官方分类整理的接口字典见 [tushare_refer/README.md](tushare_refer/README.md)：

- 基础信息：`tushare_refer/basic-info/`
- 财务数据：`tushare_refer/finance-info/`
- 行情数据：`tushare_refer/quote-info/`
- 市场参考：`tushare_refer/market-info/`
- 资金流向：`tushare_refer/moneyflow-info/`
- ETF：`tushare_refer/etf-info/`
- 指数：`tushare_refer/index-info/`
- 宏观：`tushare_refer/macro-info/`
- 港股 / 美股 / 外汇 / 黄金现货：`tushare_refer/hk-info/`、`us-info/`、`fx-info/`、`sge-info/`

积分与频次对应表见 [tushare_refer/basic-info/points_refer.md](tushare_refer/basic-info/points_refer.md)。
各接口的积分/权限要求以对应文件中的“积分/权限”段为准；部分接口要求高于 5000 积分或需单独开通权限。
