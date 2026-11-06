# =============================================================================
# Quant Data Pipeline — 常用命令
#
# 本项目只写 market.duckdb；不建 backtest.duckdb 的表。
# 默认使用 uv；若已激活自己的 Python 环境，可用 make RUN= test。
# =============================================================================

.DEFAULT_GOAL := help

UV ?= uv
RUN ?= $(UV) run
PYTHON ?= $(RUN) python
PYTEST ?= $(UV) run --with pytest python -m pytest
RUFF ?= $(UV) run --with ruff ruff

DB ?= $(DUCKDB_PATH)
START ?= 2015-01-01
END ?= 2026-11-06
STOCKS ?=
INDEXES ?=
DAILY_BASIC ?= core

.PHONY: help install install-pip hooks lint format test test-market test-factor \
        init init-factor check check-factor refresh ingest seed-index clean

help:
	@echo "Quant Data Pipeline"
	@echo ""
	@echo "  install        uv sync --extra dev"
	@echo "  test           全部测试（scripts/）"
	@echo "  test-market    warehouse 组件测试"
	@echo "  test-factor    factor 组件测试"
	@echo ""
	@echo "  init           初始化 warehouse（必须先执行）"
	@echo "  init-factor    初始化 factor 组件"
	@echo "  check          校验 warehouse"
	@echo "  check-factor   校验 factor 表 + 视图"
	@echo "  refresh        按活跃因子重建 v_factor_wide"
	@echo ""
	@echo "  ingest         Tushare -> market.duckdb（幂等）"
	@echo "  seed-index     无 index_daily 权限时的演示指数补数"
	@echo "  clean          清理缓存"
	@echo ""
	@echo "当前 DB=$(DB) START=$(START) END=$(END)"

install:
	$(UV) sync

install-pip:
	python -m pip install -e ".[dev]"

hooks:
	$(PYTHON) -m pre_commit install

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

test:
	$(PYTEST) scripts -q

test-market:
	$(PYTEST) scripts/test_init_market_db.py -q

test-factor:
	$(PYTEST) scripts/test_init_factor_db.py -q

init:
	$(PYTHON) scripts/init_market_db.py init $(if $(DB),--db "$(DB)",)

init-factor:
	$(PYTHON) scripts/init_factor_db.py init $(if $(DB),--db "$(DB)",)

check:
	$(PYTHON) scripts/init_market_db.py check $(if $(DB),--db "$(DB)",)

check-factor:
	$(PYTHON) scripts/init_factor_db.py check $(if $(DB),--db "$(DB)",)

refresh:
	$(PYTHON) scripts/init_factor_db.py refresh $(if $(DB),--db "$(DB)",)

ingest:
	$(PYTHON) scripts/ingest_market_data.py $(if $(DB),--db "$(DB)",) --start $(START) --end $(END) \
		$(if $(STOCKS),--stocks $(STOCKS),) $(if $(INDEXES),--indexes $(INDEXES),) \
		--daily-basic $(DAILY_BASIC)

seed-index:
	$(PYTHON) scripts/seed_index_demo.py $(if $(DB),--db "$(DB)",) --start $(START) --end $(END)

clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for r in (pathlib.Path('src'), pathlib.Path('scripts'), pathlib.Path('tests')) if r.exists() for p in r.rglob('__pycache__')]"
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True) for p in map(pathlib.Path, ('.pytest_cache','.ruff_cache','.mypy_cache','build','dist','htmlcov','.coverage'))]"
