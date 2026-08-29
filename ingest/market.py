"""Daily A-share bars and fund NAV used to build post-report returns."""

from __future__ import annotations

import os
import time
from datetime import date

os.environ.setdefault("TQDM_DISABLE", "1")

import akshare as ak
import pandas as pd
import requests

_EM_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_EM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}


def is_a_share(code: str) -> bool:
    text = str(code).strip()
    return text.isdigit() and len(text) == 6


def _tx_symbol(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("5", "6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def _em_secid(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("5", "6", "9")):
        return f"1.{code}"
    return f"0.{code}"


def _fetch_em_daily(code: str, start: date, end: date, timeout: float = 12) -> pd.DataFrame:
    """东财日 K：一次请求覆盖区间，不必按年探上市日。"""
    params = {
        "secid": _em_secid(code),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "smplmt": "100000",
        "lmt": "100000",
    }
    response = requests.get(_EM_KLINE, params=params, headers=_EM_HEADERS, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    klines = ((payload.get("data") or {}).get("klines")) or []
    if not klines:
        return pd.DataFrame()
    rows = []
    for item in klines:
        parts = str(item).split(",")
        if len(parts) < 3:
            continue
        rows.append({"日期": parts[0], "收盘": parts[2]})
    out = pd.DataFrame(rows)
    out["日期"] = pd.to_datetime(out["日期"]).dt.date
    out["收盘"] = pd.to_numeric(out["收盘"], errors="coerce")
    out["股票代码"] = str(code).zfill(6)
    return out.dropna(subset=["收盘"])


def _fetch_tx_daily(code: str, start: date, end: date) -> pd.DataFrame:
    frame = ak.stock_zh_a_hist_tx(
        symbol=_tx_symbol(code),
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="qfq",
        timeout=12,
    )
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.rename(columns={"date": "日期", "close": "收盘"})[["日期", "收盘"]].copy()
    out["日期"] = pd.to_datetime(out["日期"]).dt.date
    out["收盘"] = pd.to_numeric(out["收盘"], errors="coerce")
    out["股票代码"] = str(code).zfill(6)
    return out.dropna(subset=["收盘"])


def fetch_a_share_daily(code: str, start: date, end: date, retries: int = 2) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            frame = _fetch_em_daily(code, start, end)
            if frame.empty:
                return frame
            return frame
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.4 * (attempt + 1))
    try:
        return _fetch_tx_daily(code, start, end)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"price fetch failed {code}") from (last_error or exc)


def fetch_index_daily(symbol: str = "sh000688", retries: int = 3) -> pd.DataFrame:
    """Sina daily bars for a mainland index, e.g. sh000688 科创50."""
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            frame = ak.stock_zh_index_daily(symbol=symbol)
            if frame is None or frame.empty:
                return pd.DataFrame()
            out = frame.rename(columns={"date": "日期", "close": "收盘"})[["日期", "收盘"]].copy()
            out["日期"] = pd.to_datetime(out["日期"]).dt.date
            out["收盘"] = pd.to_numeric(out["收盘"], errors="coerce")
            out["指数代码"] = symbol
            return out.dropna(subset=["收盘"]).sort_values("日期")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"index fetch failed {symbol}") from last_error


def fetch_fund_nav(code: str, start: date, retries: int = 2) -> pd.DataFrame:
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
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"nav fetch failed {code}") from last_error
