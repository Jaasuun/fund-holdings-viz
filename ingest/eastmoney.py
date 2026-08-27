"""Eastmoney public-fund pulls used by ingest."""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
import requests
from akshare.utils import demjson

SCALE_URL = "https://fund.eastmoney.com/data/FundDataPortfolio_Interface.aspx"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Referer": "https://fund.eastmoney.com/data/gmbddetail.html",
}


def _decode_payload(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise ValueError(f"unexpected eastmoney payload: {text[:120]!r}")
    payload = text[start:]
    if payload.endswith(";"):
        payload = payload[:-1]
    return demjson.decode(payload)


def _get_json(params: dict, retries: int = 4) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(SCALE_URL, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return _decode_payload(response.text)
        except Exception as exc:  # noqa: BLE001 — retry network/parse flakes
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"eastmoney request failed: {params}") from last_error


def latest_report_quarter(today: date | None = None) -> str:
    """Latest calendar quarter that should already have scale filings."""
    today = today or date.today()
    quarter = (today.month - 1) // 3
    year = today.year
    if quarter == 0:
        year -= 1
        quarter = 4
    candidates = [f"{year}_{quarter}"]
    if quarter > 1:
        candidates.append(f"{year}_{quarter - 1}")
    else:
        candidates.append(f"{year - 1}_4")

    for label in candidates:
        payload = _get_json(
            {
                "dt": "8",
                "t": label,
                "pi": "1",
                "pn": "1",
                "mc": "returnJson",
                "st": "desc",
                "sc": "qmjzc",
            }
        )
        if int(payload.get("record") or 0) > 0:
            return label
    raise RuntimeError(f"no fund scale pages for quarters {candidates}")


def fetch_fund_scale(quarter: str, page_size: int = 1000, pause_s: float = 0.15) -> pd.DataFrame:
    """All funds' quarter-end NAV for one report quarter, in 亿元."""
    first = _get_json(
        {
            "dt": "8",
            "t": quarter,
            "pi": "1",
            "pn": str(page_size),
            "mc": "returnJson",
            "st": "desc",
            "sc": "qmjzc",
        }
    )
    pages = int(first.get("pages") or 0)
    rows = list(first.get("data") or [])
    for page in range(2, pages + 1):
        time.sleep(pause_s)
        payload = _get_json(
            {
                "dt": "8",
                "t": quarter,
                "pi": str(page),
                "pn": str(page_size),
                "mc": "returnJson",
                "st": "desc",
                "sc": "qmjzc",
            }
        )
        rows.extend(payload.get("data") or [])

    frame = pd.DataFrame(
        rows,
        columns=[
            "基金代码",
            "基金简称",
            "期间申购_亿份",
            "期间赎回_亿份",
            "期末总份额_亿份",
            "期末净资产_亿元",
        ],
    )
    for column in ("期间申购_亿份", "期间赎回_亿份", "期末总份额_亿份", "期末净资产_亿元"):
        frame[column] = pd.to_numeric(
            frame[column].astype(str).str.replace(",", "", regex=False),
            errors="coerce",
        )
    frame["基金代码"] = frame["基金代码"].astype(str).str.zfill(6)
    frame["报告期"] = quarter
    return frame.drop_duplicates(subset=["基金代码"], keep="first")
