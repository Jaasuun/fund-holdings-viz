"""Eastmoney public-fund pulls used by ingest."""

from __future__ import annotations

import random
import re
import time
from datetime import date
from io import StringIO

import pandas as pd
import requests
from akshare.utils import demjson
from bs4 import BeautifulSoup

SCALE_URL = "https://fund.eastmoney.com/data/FundDataPortfolio_Interface.aspx"
ARCHIVES_URL = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
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


_QUARTER_RE = re.compile(r"(\d{4})年(\d)季度")
_FULL_MONTH = {2: "6", 4: "12"}
_HOLDINGS_RENAME = {
    "占净值 比例": "占净值比例",
    "占净值比例": "占净值比例",
    "持股数（万股）": "持股数",
    "持股数 （万股）": "持股数",
    "持仓市值（万元）": "持仓市值",
    "持仓市值 （万元）": "持仓市值",
    "持仓市值（万元人民币）": "持仓市值",
    "持仓市值 （万元人民币）": "持仓市值",
}


def _get_archives(symbol: str, extra: dict[str, str], retries: int = 4) -> dict:
    last_error: Exception | None = None
    params = {
        "type": "jjcc",
        "code": symbol,
        "rt": f"{random.random():.16f}",
        **extra,
    }
    headers = {
        **HEADERS,
        "Referer": f"https://fundf10.eastmoney.com/ccmx_{symbol}.html",
        "X-Requested-With": "XMLHttpRequest",
    }
    for attempt in range(retries):
        try:
            response = requests.get(ARCHIVES_URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return _decode_payload(response.text)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"eastmoney holdings failed: {symbol} {extra}") from last_error


def _normalize_holdings_table(frame: pd.DataFrame, title: str) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [str(col).replace("\xa0", " ").strip() for col in frame.columns]
    frame = frame.rename(columns=_HOLDINGS_RENAME)
    drop_cols = [col for col in ("相关资讯", "最新价", "涨跌幅") if col in frame.columns]
    frame = frame.drop(columns=drop_cols, errors="ignore")
    if "股票代码" not in frame.columns:
        return pd.DataFrame()
    frame["股票代码"] = frame["股票代码"].map(_norm_stock_code)
    if "占净值比例" in frame.columns:
        frame["占净值比例"] = (
            frame["占净值比例"].astype(str).str.replace("%", "", regex=False)
        )
    for column in ("占净值比例", "持股数", "持仓市值"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    match = _QUARTER_RE.search(title.replace("\xa0", " "))
    frame["季度标题"] = title
    frame["报告年"] = int(match.group(1)) if match else pd.NA
    frame["报告季"] = int(match.group(2)) if match else pd.NA
    keep = [col for col in ("股票代码", "股票名称", "占净值比例", "持股数", "持仓市值", "报告年", "报告季") if col in frame.columns]
    return frame[keep]


def _norm_stock_code(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0") and text.replace(".0", "").isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    return text


def _parse_holdings_payload(payload: dict) -> pd.DataFrame:
    content = payload.get("content") or ""
    if not str(content).strip():
        return pd.DataFrame()
    soup = BeautifulSoup(content, features="lxml")
    titles = [item.get_text(" ", strip=True) for item in soup.find_all(name="h4", attrs={"class": "t"})]
    tables = pd.read_html(StringIO(str(content)), converters={"股票代码": str})
    parts = []
    for title, table in zip(titles, tables, strict=False):
        part = _normalize_holdings_table(table, title)
        if not part.empty:
            parts.append(part)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def _pick_quarter(frame: pd.DataFrame, year: int, quarter: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    picked = frame[(frame["报告年"] == year) & (frame["报告季"] == quarter)].copy()
    return picked.reset_index(drop=True)


def fetch_fund_stock_holdings(symbol: str, year: int, quarter: int, pause_s: float = 0.2) -> pd.DataFrame:
    """Prefer 中报/年报 complete book; fall back to quarterly top-10."""
    month = _FULL_MONTH.get(quarter, "")
    picked = pd.DataFrame()
    source = "前十大"
    if month:
        payload = _get_archives(symbol, {"topline": "10000", "year": str(year), "month": month})
        picked = _pick_quarter(_parse_holdings_payload(payload), year, quarter)
        if len(picked) > 10:
            source = "全部持股"
        time.sleep(pause_s)
    if source != "全部持股":
        payload = _get_archives(symbol, {"topline": "10", "year": str(year), "month": ""})
        fallback = _pick_quarter(_parse_holdings_payload(payload), year, quarter)
        if not fallback.empty:
            picked = fallback
        source = "前十大"
    if picked.empty:
        return picked
    out = picked.copy()
    out["基金代码"] = str(symbol).zfill(6)
    out["披露口径"] = source
    out["报告期"] = f"{year}_{quarter}"
    out.insert(0, "序号", range(1, len(out) + 1))
    return out
