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

```bash
python scripts/ingest_market_data.py \
    --db "${MARKET_DB_PATH}" \
    --start 2015-01-01 --end 2026-11-06 \
    --stocks 600519.SH,000858.SZ,... \
    --indexes 000300.SH,000905.SH,000852.SH \
    --daily-basic core \
    --with-index-weight
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--db` | `DUCKDB_PATH` | market.duckdb 路径 |
| `--start` / `--end` | `2015-01-01` / 今天 | `YYYY-MM-DD` |
| `--calendar` | `SSE` | 交易日历交易所 |
| `--stocks` | 20 只样本股 | 逗号分隔；传空跳过个股 |
| `--indexes` | `000300.SH,000905.SH,000852.SH` | 逗号分隔；传空跳过指数 |
| `--funds` | 空 | 逗号分隔的 ETF |
| `--daily-basic` | `core` | `all` / `core`（前 5 只）/ `none` |
| `--with-index-weight` | 关 | 需要 Tushare 权限 |

## 3. 幂等与主键

| 表 | 幂等键 |
| --- | --- |
| `dim_trade_cal` | `(exchange, cal_date)` |
| `dim_stock_basic` | `ts_code` |
| `fact_daily` | `(ts_code, trade_date)` |
| `fact_adj_factor` | `(ts_code, trade_date)` |
| `fact_daily_basic` | `(ts_code, trade_date)` |
| `fact_index_daily` | `(index_code, trade_date)` |
| `fact_index_weight` | `(index_code, trade_date, con_code)` |
| `fact_fund_daily` | `(ts_code, trade_date)` |

写入使用 `INSERT INTO ... BY NAME SELECT * FROM <registered frame> ON CONFLICT
(keys) DO UPDATE`，同一标的重复拉取只覆盖，不追加。

## 4. 限频与权限降级

Tushare 不同积分档位的接口频率差异很大。脚本按以下策略降级：

| 情况 | 行为 |
| --- | --- |
| `trade_cal` 被限频 | 记录 failed，后续从 `fact_daily` 的实际交易日反推 |
| `stock_basic` 被限频 | 记录 failed，不阻断日线 |
| `adj_factor` 被限频 | 跳过该标的复权因子；`fact_daily.pct_chg` 仍可用于收益 |
| `daily_basic` 被限频 | 跳过；市值加权基准需等该表补齐后再启用 |
| `fund_daily` 无权限 | 记录 failed，ETF 基准保持 `enabled: false` |
| `index_weight` 无权限 | 首次失败即停止后续月份，动态标的池不可用 |

`TushareSource` 对“频/超限/权限/积分”类错误**不做指数退避重试**，避免继续消耗额度；
网络类错误仍会重试 3 次。

## 5. 低积分 token 的推荐顺序

1. 先拉个股日线（`daily` 通常额度较高）：
   ```bash
   python scripts/ingest_market_data.py --indexes= --daily-basic none
   ```
2. 隔一段时间补 `adj_factor` / `daily_basic`（默认 `core` 只补 5 只）。
3. `index_daily` 有权限时单独补指数；没有权限可用
   `scripts/seed_index_demo.py` 拉公开 K 线，仅用于打通流程。
4. `index_weight` 有权限后再启用 `BI_EQW_HS300`。

## 6. 调度建议

- 交易日收盘后（18:00 之后）执行一次；重复执行安全。
- 增量区间可用 `--start <最近N天> --end 今天`，靠 upsert 覆盖修订。
- 大规模全市场回补建议按年份分段，避免单次请求/内存过大。

## 7. 元数据

每次表级写入都会 upsert `meta_ingest_log`：

| 字段 | 说明 |
| --- | --- |
| `table_name` | 目标表 |
| `scope_key` | 范围键，如 `600519.SH:2015-01-01:2026-11-06` |
| `row_count` | 写入行数 |
| `status` | `ok` / `failed` |
| `detail` | 本批各表行数或错误摘要 |
| `started_at` / `finished_at` | 起止时间 |

同一 `(table_name, scope_key)` 重复执行会覆盖日志，不膨胀。

## 8. 常见问题

- **`ModuleNotFoundError: six`**：Tushare 依赖缺失，`uv add tushare` 应自动安装；手动环境可 `uv pip install six`。
- **`index_daily` 报权限**：不是代码问题，是 token 积分；用 `seed_index_demo.py` 或升级权限。
- **写入时报主键冲突**：说明 market 库是旧版本（没有主键）。本仓库默认新建；
  旧库需要迁移/重建后再用 upsert。
- **DuckDB 文件被占用**：同一文件只允许一个 RW 连接；确认没有另一个初始化/写入进程。
