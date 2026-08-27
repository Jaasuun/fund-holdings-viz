"""Build daily fund returns from frozen report holdings and official NAV."""

from __future__ import annotations

from calendar import monthrange
from datetime import date

import pandas as pd

from ingest.market import is_a_share


def report_end(label: str) -> date:
    year, quarter = (int(part) for part in label.split("_"))
    month = quarter * 3
    return date(year, month, monthrange(year, month)[1])


def implied_daily_returns(holdings: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    book = holdings.copy()
    book["股票代码"] = book["股票代码"].astype(str)
    book = book[book["股票代码"].map(is_a_share)]
    book["权重"] = pd.to_numeric(book["占净值比例"], errors="coerce").fillna(0.0) / 100.0
    if book.empty or prices.empty:
        return pd.DataFrame(columns=["基金代码", "日期", "推算涨幅", "覆盖净值比例"])

    close = prices.copy()
    close["日期"] = pd.to_datetime(close["日期"]).dt.date
    pivot = close.pivot_table(index="日期", columns="股票代码", values="收盘", aggfunc="last").sort_index()
    pivot = pivot.ffill()
    stock_ret = pivot.pct_change()

    parts: list[pd.DataFrame] = []
    for fund_code, group in book.groupby("基金代码"):
        weights = group.drop_duplicates("股票代码").set_index("股票代码")["权重"]
        cols = [code for code in weights.index if code in stock_ret.columns]
        if not cols:
            continue
        rets = stock_ret[cols]
        aligned = weights.reindex(cols).fillna(0.0)
        implied = rets.mul(aligned, axis=1).sum(axis=1)
        coverage = float(aligned.sum())
        part = pd.DataFrame(
            {
                "基金代码": str(fund_code).zfill(6),
                "日期": implied.index,
                "推算涨幅": implied.to_numpy(),
                "覆盖净值比例": coverage,
            }
        )
        parts.append(part)
    if not parts:
        return pd.DataFrame(columns=["基金代码", "日期", "推算涨幅", "覆盖净值比例"])
    out = pd.concat(parts, ignore_index=True)
    out = out.dropna(subset=["推算涨幅"])
    return out


def merge_returns(nav: pd.DataFrame, implied: pd.DataFrame, start: date) -> pd.DataFrame:
    nav = nav.copy()
    nav["日期"] = pd.to_datetime(nav["日期"]).dt.date
    nav["基金代码"] = nav["基金代码"].astype(str).str.zfill(6)
    implied = implied.copy()
    implied["日期"] = pd.to_datetime(implied["日期"]).dt.date
    implied["基金代码"] = implied["基金代码"].astype(str).str.zfill(6)
    frame = nav.merge(implied, on=["基金代码", "日期"], how="outer")
    frame = frame[frame["日期"] > start].copy()
    frame = frame.sort_values(["基金代码", "日期"])

    def _cum(series: pd.Series) -> pd.Series:
        valid = series.dropna()
        if valid.empty:
            return pd.Series(pd.NA, index=series.index)
        return ((1.0 + valid).cumprod() - 1.0).reindex(series.index)

    frame["实际累计"] = frame.groupby("基金代码")["实际涨幅"].transform(_cum)
    frame["推算累计"] = frame.groupby("基金代码")["推算涨幅"].transform(_cum)
    return frame.reset_index(drop=True)


def latest_return_board(daily: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return daily
    actual = daily.dropna(subset=["实际涨幅"])
    snapshot = actual["日期"].max() if not actual.empty else daily["日期"].max()
    latest = daily[daily["日期"] == snapshot].copy()
    latest = latest.drop(columns=[col for col in ("产品名称", "代表简称", "基金类型", "规模_亿元") if col in latest.columns])
    meta = universe[["代表代码", "产品名称", "代表简称", "基金类型", "规模_亿元"]].copy()
    meta["基金代码"] = meta["代表代码"].astype(str).str.zfill(6)
    board = latest.merge(meta, on="基金代码", how="left")
    board = board.sort_values("实际涨幅", ascending=False, na_position="last").reset_index(drop=True)
    board.insert(0, "序号", range(1, len(board) + 1))
    return board
