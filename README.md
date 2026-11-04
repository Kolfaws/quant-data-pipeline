# Quant Data Pipeline

一个模块化的量化数据管道，负责数据源拉取（Fetch）、数据清洗（Clean）、增量更新（Update）以及底层数据库结构初始化（Init）。

**目前仅支持 Daily 数据，默认数据源 = Tushare。**

> **开发状态**：`core/`、`processors/`、`sources/`、`sinks/` 仍为占位模块；数据库初始化（`scripts/init_*.py`）已可用，管道 CLI 尚在建设中。

## 1. 架构总览

本项目按职责分为几个核心模块，数据层采用单库多组件架构：`warehouse` 与 `factor` 共用同一个 DuckDB 文件。

- **Warehouse 组件（基础库）**：基于 DuckDB 初始化基础行情结构、建表、建视图（`scripts/init_market_db.py`）。该组件作为单一数据源，结构保持稳定。
- **Factor 组件（因子层）**：factor 组件追加在同一个 DuckDB 文件中（`scripts/init_factor_db.py`），通过 `meta_schema_version` 里 `component = 'factor'` 的版本行与 warehouse 隔离。因子表与宽表视图可以直接 JOIN 行情表，无需跨库 `ATTACH`。
- **Fetch**：从外部数据源（如 Tushare 等）拉取原始数据（`src/data_pipeline/core/source.py`）。
- **Clean**：对原始数据进行清洗、去重、格式转换（`src/data_pipeline/processors/cleaner.py`）。
- **Update**：增量更新历史数据到 DuckDB（`src/data_pipeline/cli.py` 调度）。
- **Sink**：负责将处理好的数据写入数据库（`src/data_pipeline/core/sink.py`）。

> **单库原因**：DuckDB 的写锁以文件为单位，拆成两个文件并不能解决单写者冲突，反而会让 `v_factor_valid` 必须跨库 `ATTACH`。拆库阈值与迁移方案见 [docs/init_factor_db.md](docs/init_factor_db.md) 第 12 节。

## 2. 快速开始

### 2.1 环境准备

```bash
# 推荐：uv（由 pyproject.toml / .python-version 管理）
uv sync --extra dev
# 或
make install

# 也可以在已激活的虚拟环境中可编辑安装
pip install -e ".[dev]"

# 或安装完整环境快照（包含研究/回测依赖，体积较大）
pip install -r requirements.txt
```

要求 Python >= 3.10。

### 2.2 配置环境变量

复制 `.env.example` 为 `.env`，填入数据源 Token 与数据库路径：

```env
# 单库：warehouse 与 factor 共用同一个 DuckDB 文件
DUCKDB_PATH=data/market.duckdb
TUSHARE_TOKEN=your_token_here

# FACTOR_DB_PATH 已废弃：factor 与 warehouse 必须同库。
```

### 2.3 初始化数据库

```bash
# 1) 初始化 warehouse 组件（必须先执行）
python scripts/init_market_db.py init --db data/market.duckdb

# 2) 初始化 factor 组件（会检查 warehouse 版本 >= 1.1.0）
python scripts/init_factor_db.py init --db data/market.duckdb

# 3) 校验结构；因子目录变更后刷新宽表视图
python scripts/init_factor_db.py check   --db data/market.duckdb
python scripts/init_factor_db.py refresh --db data/market.duckdb
```

两个脚本必须指向同一个库文件，并按 `warehouse → factor` 的顺序执行。DuckDB 是跨进程单写者，初始化期间不要并发写入。

等价的 Makefile 命令：

```bash
make init          # warehouse
make init-factor   # factor
make check         # warehouse 结构校验
make check-factor  # factor 结构 + 视图校验
make refresh       # 按当前活跃因子重建 v_factor_wide
```

> 表结构与实现约定详见：
>
> - [Warehouse 组件初始化文档](docs/init_market_db.md)
> - [Factor 组件初始化文档](docs/init_factor_db.md)

### 2.4 运行数据管道

```bash
# 说明：cli.py 当前为占位，以下为规划中的模块接口
python -m data_pipeline.cli fetch  --date 20240101
python -m data_pipeline.cli clean  --date 20240101
python -m data_pipeline.cli update --date 20240101

# 安装后也可使用 console script
quant-data-pipeline fetch --date 20240101
```

## 3. 目录结构

```text
quant-data-pipeline/
├── data/                       # 本地数据目录（实际数据文件被 .gitignore 忽略）
│   ├── raw/                    # 原始数据（JSON / CSV 等）
│   ├── processed/              # 清洗后的中间数据
│   └── market.duckdb           # 单库文件：warehouse + factor 两组件共用（init 后生成）
├── docs/                       # 详细设计文档
│   ├── init_market_db.md       # warehouse 组件：表结构、API、版本记录
│   └── init_factor_db.md       # factor 组件：表结构、宽表视图、复杂度与权衡
├── scripts/                    # 可独立执行的脚本（不依赖包安装）
│   ├── init_market_db.py       # warehouse 组件建表 / 建视图 / 校验
│   ├── init_factor_db.py       # factor 组件建表 / 建视图 / 校验 / refresh
│   ├── test_init_market_db.py  # warehouse 组件测试
│   └── test_init_factor_db.py  # factor 组件与跨组件测试
├── src/data_pipeline/          # 管道 Python 包（src 布局）
│   ├── core/                   # 核心抽象：Source / Sink 基类（占位）
│   ├── processors/             # 数据清洗逻辑：cleaner（占位）
│   ├── sources/                # 具体数据源实现：tushare（占位）
│   ├── sinks/                  # 具体落库实现：duckdb_sink / parquet_sink
│   ├── cli.py                  # 管道命令行入口（占位）
│   ├── config.py               # 全局配置：读取 .env
│   └── logger.py               # loguru 日志配置
├── tests/                      # 包级单元测试目录
├── .env.example                # 环境变量模板（复制为 .env）
├── .gitattributes              # 换行符与二进制文件规则
├── .gitignore                  # Git 忽略规则
├── .pre-commit-config.yaml     # pre-commit 钩子（ruff / codespell 等）
├── .python-version             # Python 版本（3.10）
├── Makefile                    # 常用开发、测试与数据库初始化命令
├── pyproject.toml              # 项目元数据、依赖、ruff / pytest 配置
├── requirements.txt            # 完整环境依赖快照（pip freeze）
└── README.md                   # 本文件
```

## 4. 各模块说明

### 4.1 Warehouse 组件初始化 (`init_market_db`)

负责 `warehouse` 组件的建表、建视图、记录版本号。幂等且严格校验结构（缺表、缺列、类型不符、多余列都会失败），作为整个系统唯一的基础数据来源。详见 [docs/init_market_db.md](docs/init_market_db.md)。

### 4.2 因子组件初始化 (`init_factor_db`)

在同一个 DuckDB 文件中追加 factor 表、视图与 `component = 'factor'` 版本行。必须先完成 `init_market_db`（warehouse 版本 >= `1.1.0`），否则在建表前直接 `SchemaError` 失败；因子目录（`meta_factor_registry`）变更后必须执行 `refresh` 重建 `v_factor_wide`，否则宽表列不会更新。详见 [docs/init_factor_db.md](docs/init_factor_db.md)。

### 4.3 数据拉取 (`fetch`)

负责从数据源按指定日期或范围拉取原始数据存入 `data/raw` 或直接流转。

### 4.4 数据清洗 (`clean`)

负责处理空值、类型转换、去重等。

### 4.5 数据更新 (`update`)

负责将清洗后的数据写入 DuckDB，包含增量逻辑与幂等写入（如 `ON CONFLICT`）。

## 5. 开发与测试

```bash
# 安装 / 同步依赖
make install

# 运行全部测试（tests/ 与 scripts/）
make test
# 只跑数据库初始化相关测试
make test-market
make test-factor

# 代码检查与格式化
make lint
make format

# 查看全部命令
make help
```

> 默认通过 `uv run` 执行。若使用已激活的 conda / venv 环境而非 uv，可清空运行器：
>
> ```bash
> make RUN= test
> make RUN= init
> ```
>
> 或直接调用 `python scripts/init_market_db.py ...` / `pytest ...`。

直接使用 pytest：

```bash
pytest -q scripts/test_init_market_db.py scripts/test_init_factor_db.py
```

> Windows 下 POSIX 文件权限相关用例会自动跳过，其余用例应全绿。

---
END OF FILE
