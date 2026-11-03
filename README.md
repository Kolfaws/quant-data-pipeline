# Under Construction Uncomplete

**missing: core/, processors/, sources/, sinks/**

# Quant Data Pipeline

一个模块化的量化数据管道，负责数据源拉取（Fetch）、数据清洗（Clean）、增量更新（Update）以及底层数据库结构初始化（Init）

**目前仅支持Daily数据, default-source=Tushare**

## 1. 架构总览

本项目按职责分为几个核心模块：

- **Init DB**：基于 DuckDB 初始化量化库结构、建表、建视图（`scripts/init_duckdb.py`）。
- **Fetch**：从外部数据源（如 Tushare 等）拉取原始数据（`src/data_pipeline/core/source.py`）。
- **Clean**：对原始数据进行清洗、去重、格式转换（`src/data_pipeline/processors/cleaner.py`）。
- **Update**：增量更新历史数据到 DuckDB（`src/data_pipeline/cli.py` 调度）。
- **Sink**：负责将处理好的数据写入数据库（`src/data_pipeline/core/sink.py`）。

## 2. 快速开始

### 2.1 环境准备

```bash
pip install -r requirements.txt  # 假设你有这个文件
# 或
pip install duckdb tushare pandas pydantic
```

### 2.2 配置环境变量

复制 `.env.example` 为 `.env`，填入你的数据源 Token 和数据库路径。

```env
DUCKDB_PATH=data/market.duckdb
TUSHARE_TOKEN=your_token_here
```

### 2.3 初始化数据库

```bash
python scripts/init_duckdb.py init
```

> 表结构与实现约定详见[数据库初始化文档](docs/init_duckdb.md)。

### 2.4 运行数据管道

```bash
# 拉取数据
python -m src.data_pipeline.cli fetch --date 20240101
# 清洗数据
python -m src.data_pipeline.cli clean --date 20240101
# 更新入库
python -m src.data_pipeline.cli update --date 20240101
```

## 3. 目录结构

```text
quant-data-pipeline/
├── data/                   # 数据存放目录 (raw / processed)
├── docs/                   # 详细文档
│   ├── init_duckdb.md      # DuckDB 结构初始化说明 (核心)
│   └── database_schema.md  # (可选) 表结构速查
├── scripts/                # 独立执行脚本
│   ├── init_duckdb.py
│   └── test_init_duckdb.py
├── src/data_pipeline/
│   ├── core/               # 核心抽象 (source, sink)
│   ├── processors/         # 数据清洗逻辑 (cleaner)
│   ├── sources/            # 具体数据源实现
│   ├── sinks/              # 具体落库实现
│   ├── cli.py              # 管道命令行入口
│   ├── config.py           # 全局配置
│   └── logger.py           # 日志配置
└── tests/                  # 单元测试
```

## 4. 各模块说明

### 4.1 数据库初始化 (`init_duckdb`)

负责建表、建视图、记录版本号。幂等且严格校验结构。详见 [docs/init_duckdb.md](docs/init_duckdb.md)。

### 4.2 数据拉取 (`fetch`)

负责从数据源按指定日期或范围拉取原始数据存入 `data/raw` 或直接流转。

### 4.3 数据清洗 (`clean`)

负责处理空值、类型转换、去重等。

### 4.4 数据更新 (`update`)

负责将清洗后的数据写入 DuckDB，包含增量逻辑与幂等写入（如 `ON CONFLICT`）。

## 5. 开发与测试

```bash
# 运行测试
pytest -q
```

---

END OF FILE
