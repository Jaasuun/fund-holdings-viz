"""Daily A-share bars and fund NAV used to build post-report returns."""

from __future__ import annotations

import time
from datetime import date

import akshare as ak
import pandas as pd


def is_a_share(code: str) -> bool:
    text = str(code).strip()
    return text.isdigit() and len(text) == 6


def _tx_symbol(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("5", "6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def fetch_a_share_daily(code: str, start: date, end: date, retries: int = 1) -> pd.DataFrame:
    symbol = _tx_symbol(code)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            frame = ak.stock_zh_a_hist_tx(
                symbol=symbol,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            )
            if frame is None or frame.empty:
                return pd.DataFrame()
            out = frame.rename(columns={"date": "日期", "close": "收盘"})[["日期", "收盘"]].copy()
            out["日期"] = pd.to_datetime(out["日期"]).dt.date
            out["收盘"] = pd.to_numeric(out["收盘"], errors="coerce")
            out["股票代码"] = str(code).zfill(6)
            return out.dropna(subset=["收盘"])
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"price fetch failed {code}") from last_error


def fetch_fund_nav(code: str, start: date, retries: int = 3) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            frame = ak.fund_open_fund_info_em(symbol=str(code).zfill(6), indicator="单位净值走势")
            if frame is None or frame.empty:
                return pd.DataFrame()
            out = frame.copy()
            out["日期"] = pd.to_datetime(out["净值日期"]).dt.date
            out = out[out["日期"] >= start]
            out["单位净值"] = pd.to_numeric(out["单位净值"], errors="coerce")
            out["实际涨幅"] = pd.to_numeric(out["日增长率"], errors="coerce") / 100.0
            out["基金代码"] = str(code).zfill(6)
            return out[["基金代码", "日期", "单位净值", "实际涨幅"]].dropna(subset=["单位净值"])
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"nav fetch failed {code}") from last_error
