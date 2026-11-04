# =============================================================================
# Quant Data Pipeline — 常用开发与数据库初始化命令
#
# 默认使用 uv（项目由 uv 初始化，见 .python-version / pyproject.toml）：
#   make install          # uv sync --extra dev
#   make test
#
# 若已激活自己的 Python 环境（如 conda quant），可关闭 uv 运行器：
#   make RUN= test
# =============================================================================

.DEFAULT_GOAL := help

UV ?= uv
RUN ?= $(UV) run --extra dev
PYTHON ?= $(RUN) python
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
SYS_PYTHON ?= python

DB ?= data/market.duckdb
THREADS ?= 6
MEMORY_LIMIT ?= 6GB
PYTEST_ARGS ?=

.PHONY: help install install-pip sync test test-market test-factor lint format \
        pre-commit init init-market init-factor check check-market check-factor \
        refresh build clean

help:
	@echo Quant Data Pipeline
	@echo.
	@echo 用法: make TARGET [DB=...] [THREADS=...] [MEMORY_LIMIT=...]
	@echo.
	@echo 环境:
	@echo   install        安装/同步运行与开发依赖 (uv sync --extra dev)
	@echo   install-pip    使用当前 Python 环境可编辑安装 (pip install -e .[dev])
	@echo   sync           install 的别名
	@echo   build          构建 sdist + wheel (uv build)
	@echo.
	@echo 测试与质量:
	@echo   test           运行全部测试
	@echo   test-market    仅 warehouse 组件测试
	@echo   test-factor    仅 factor 组件测试
	@echo   lint           ruff check
	@echo   format         ruff format（会修改文件）
	@echo   pre-commit     运行全部 pre-commit 钩子
	@echo.
	@echo 数据库 (单库多组件):
	@echo   init           初始化 warehouse 组件（必须先执行）
	@echo   init-factor    追加 factor 组件
	@echo   check          校验 warehouse 结构
	@echo   check-factor   校验 factor 结构与视图
	@echo   refresh        按因子目录重建 v_factor_wide
	@echo   clean          清理缓存与构建产物
	@echo.
	@echo 当前: DB=$(DB) THREADS=$(THREADS) MEMORY_LIMIT=$(MEMORY_LIMIT)

install:
	$(UV) sync --extra dev

install-pip:
	$(SYS_PYTHON) -m pip install -e ".[dev]"

sync: install

test:
	$(PYTEST) $(PYTEST_ARGS)

test-market:
	$(PYTEST) -q scripts/test_init_market_db.py $(PYTEST_ARGS)

test-factor:
	$(PYTEST) -q scripts/test_init_factor_db.py $(PYTEST_ARGS)

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

pre-commit:
	$(PYTHON) -m pre_commit run --all-files

init:
	$(PYTHON) scripts/init_market_db.py init --db $(DB) --threads $(THREADS) --memory-limit $(MEMORY_LIMIT)

init-market: init

init-factor:
	$(PYTHON) scripts/init_factor_db.py init --db $(DB) --threads $(THREADS) --memory-limit $(MEMORY_LIMIT)

check:
	$(PYTHON) scripts/init_market_db.py check --db $(DB) --threads $(THREADS) --memory-limit $(MEMORY_LIMIT)

check-market: check

check-factor:
	$(PYTHON) scripts/init_factor_db.py check --db $(DB) --threads $(THREADS) --memory-limit $(MEMORY_LIMIT)

refresh:
	$(PYTHON) scripts/init_factor_db.py refresh --db $(DB) --threads $(THREADS) --memory-limit $(MEMORY_LIMIT)

build:
	$(UV) build

clean:
	$(PYTHON) -c "import pathlib, shutil; roots=[pathlib.Path(p) for p in ('src','scripts','tests') if pathlib.Path(p).exists()]; [shutil.rmtree(p, ignore_errors=True) for r in roots for p in r.rglob('__pycache__')]"
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True) for p in map(pathlib.Path, ('.pytest_cache','.ruff_cache','.mypy_cache','build','dist','htmlcov','.coverage'))]"
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('*.egg-info')]"
