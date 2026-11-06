"""sources.tushare_src — Tushare 只读数据源。

职责边界：
* 只负责“Tushare -> polars DataFrame”，不做清洗、不做落库；
* 输出列名与 ``quant_schema.market_ddl`` 对齐，日期转成 ``pl.Date``；
* 网络/权限错误统一包装为 :class:`~data_pipeline.core.errors.FetchError`。

落库由 ``scripts/ingest_market_data.py`` 负责，只写 ``market.duckdb``。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Final

import polars as pl

from ..core.errors import ConfigError, FetchError

LOG = logging.getLogger("data_pipeline.tushare")

_DATE_COLS: Final[dict[str, tuple[str, ...]]] = {
    "trade_cal": ("cal_date", "pretrade_date"),
    "stock_basic": ("list_date", "delist_date"),
    "daily": ("trade_date",),
    "adj_factor": ("trade_date",),
    "daily_basic": ("trade_date",),
    "index_daily": ("trade_date",),
    "fund_daily": ("trade_date",),
    "index_weight": ("trade_date",),
}


class TushareSource:
    """轻量 Tushare 客户端（带限频与重试）。

    Args:
        token: Tushare token；``None`` 时读取环境变量 ``TUSHARE_TOKEN``。
        calls_per_minute: 调用频率上限。
        retry_attempts: 单个接口失败重试次数（不含首次）。
        backoff_seconds: 指数退避初始秒数。
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        calls_per_minute: int = 180,
        retry_attempts: int = 3,
        backoff_seconds: float = 2.0,
    ) -> None:
        import os

        self._token = token or os.getenv("TUSHARE_TOKEN")
        self._calls_per_minute = max(1, int(calls_per_minute))
        self._retry_attempts = max(0, int(retry_attempts))
        self._backoff_seconds = max(0.0, float(backoff_seconds))
        self._last_call = 0.0
        self._pro: Any | None = None

    # ------------------------------------------------------------------ 基础
    @property
    def pro(self) -> Any:
        if self._pro is not None:
            return self._pro
        if not self._token:
            raise ConfigError("缺少 TUSHARE_TOKEN：请在 .env 或环境变量中配置")
        try:
            import tushare as ts
        except ImportError as exc:  # pragma: no cover - 环境问题
            raise ConfigError("未安装 tushare：请执行 uv add tushare") from exc
        try:
            self._pro = ts.pro_api(self._token)
        except Exception as exc:  # pragma: no cover - token 非法
            raise ConfigError(f"Tushare 初始化失败：{exc}") from exc
        return self._pro

    def _throttle(self) -> None:
        interval = 60.0 / self._calls_per_minute
        wait = interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _call(self, api_name: str, **params: Any) -> pl.DataFrame:
        """调用 Tushare 接口并转成 polars；空结果返回空表而非异常。"""
        last_error: Exception | None = None
        for attempt in range(self._retry_attempts + 1):
            self._throttle()
            try:
                raw = getattr(self.pro, api_name)(**params)
                break
            except Exception as exc:
                last_error = exc
                message = str(exc)
                # 限频/权限类错误重试只会继续消耗额度，直接失败让调用方降级。
                if any(token in message for token in ("频", "超限", "权限", "积分")):
                    raise FetchError(
                        f"Tushare 接口 {api_name} 不可用（参数 {params}）：{message}"
                    ) from exc
                if attempt >= self._retry_attempts:
                    raise FetchError(
                        f"Tushare 接口 {api_name} 失败（参数 {params}）：{exc}"
                    ) from exc
                sleep_s = self._backoff_seconds * (2**attempt)
                LOG.warning(
                    "Tushare %s 第 %d 次失败，%.1fs 后重试：%s",
                    api_name,
                    attempt + 1,
                    sleep_s,
                    exc,
                )
                time.sleep(sleep_s)
        else:  # pragma: no cover - 循环必定 break 或 raise
            raise FetchError(f"Tushare 接口 {api_name} 失败：{last_error}")

        if raw is None:
            return pl.DataFrame()
        return self._to_polars(raw, api_name, params)

    @staticmethod
    def _to_polars(raw: Any, api_name: str, params: dict[str, Any]) -> pl.DataFrame:
        try:
            # 不依赖 pyarrow：pandas -> dict-of-lists -> polars
            frame = pl.DataFrame(raw.to_dict(orient="list"))
        except Exception as exc:  # pragma: no cover - 异常返回结构
            raise FetchError(f"Tushare {api_name} 返回结构无法转换：{exc}") from exc

        if api_name == "daily" and "change" in frame.columns:
            frame = frame.rename({"change": "chg"})
        elif api_name == "index_daily":
            mapping = {"ts_code": "index_code", "change": "chg"}
            frame = frame.rename(
                {old: new for old, new in mapping.items() if old in frame.columns}
            )
        elif api_name == "fund_daily" and "change" in frame.columns:
            frame = frame.rename({"change": "chg"})

        for column in _DATE_COLS.get(api_name, ()):
            if column in frame.columns:
                frame = frame.with_columns(
                    pl.col(column)
                    .cast(pl.Utf8)
                    .str.strptime(pl.Date, "%Y%m%d", strict=False)
                )

        if api_name == "trade_cal" and "is_open" in frame.columns:
            frame = frame.with_columns(pl.col("is_open").cast(pl.Int8).cast(pl.Boolean))

        LOG.debug("Tushare %s 返回 %d 行，参数=%s", api_name, frame.height, params)
        return frame

    # ------------------------------------------------------------------ 接口
    def fetch_trade_cal(
        self, start: str, end: str, exchange: str = "SSE"
    ) -> pl.DataFrame:
        return self._call(
            "trade_cal", exchange=exchange, start_date=start, end_date=end
        )

    def fetch_stock_basic(self, list_status: str = "L") -> pl.DataFrame:
        return self._call("stock_basic", exchange="", list_status=list_status)

    def fetch_daily(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        return self._call("daily", ts_code=ts_code, start_date=start, end_date=end)

    def fetch_adj_factor(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        return self._call("adj_factor", ts_code=ts_code, start_date=start, end_date=end)

    def fetch_daily_basic(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        return self._call(
            "daily_basic", ts_code=ts_code, start_date=start, end_date=end
        )

    def fetch_index_daily(self, index_code: str, start: str, end: str) -> pl.DataFrame:
        return self._call(
            "index_daily", ts_code=index_code, start_date=start, end_date=end
        )

    def fetch_fund_daily(self, ts_code: str, start: str, end: str) -> pl.DataFrame:
        return self._call("fund_daily", ts_code=ts_code, start_date=start, end_date=end)

    def fetch_index_weight(self, index_code: str, trade_date: str) -> pl.DataFrame:
        return self._call("index_weight", index_code=index_code, trade_date=trade_date)


__all__ = ["TushareSource"]
