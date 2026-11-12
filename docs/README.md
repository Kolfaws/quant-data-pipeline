# quant-data-pipeline 文档索引

面向代码助手按需读取。安装、配置、命令和风险见 [../README.md](../README.md)。

| 文档 | 何时读 | 内容 |
| --- | --- | --- |
| [init_market_db.md](init_market_db.md) | 改 warehouse 表/视图、初始化或校验库时 | market.duckdb 的 warehouse DDL、版本、视图、CLI |
| [init_factor_db.md](init_factor_db.md) | 改 factor 表/视图、写因子、做可交易过滤时 | factor DDL、宽表视图、因子有效性过滤 |
| [ingest_market_data.md](ingest_market_data.md) | 改 Tushare 摄入、限频、降级或补数时 | 接口、字段、限频、fallback 和测试库流程 |

## Tushare 接口字典

[`tushare_refer/`](tushare_refer/README.md) 是 Tushare 接口字典库，按分类
存放单个接口文档。**默认不要读取整个目录**；需要某个接口时，按接口名查：

```text
tushare_refer/<category>/<api>.md
```

例如 `quote-info/daily.md`、`bond-info/cb_basic.md`。字典只用于查字段、
积分和调用示例，不作为项目设计文档阅读。
