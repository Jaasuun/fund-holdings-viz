"""Turn per-fund holdings into a stock-level table."""

from __future__ import annotations

import pandas as pd


def fund_codes(holdings: pd.DataFrame) -> set[str]:
    if holdings.empty or "基金代码" not in holdings.columns:
        return set()
    return set(holdings["基金代码"].astype(str).str.zfill(6))


def common_fund_codes(holdings: pd.DataFrame) -> set[str]:
    """Funds that appear in every report period present in the frame.

    Cross-quarter stock rankings are only meaningful on this intersection.
    """
    if holdings.empty or "基金代码" not in holdings.columns:
        return set()
    if "报告期" not in holdings.columns:
        return fund_codes(holdings)
    periods = [str(p) for p in holdings["报告期"].astype(str).unique().tolist()]
    if len(periods) <= 1:
        return fund_codes(holdings)
    sets = [
        fund_codes(holdings[holdings["报告期"].astype(str) == period])
        for period in periods
    ]
    return set.intersection(*sets) if sets else set()


def filter_to_funds(holdings: pd.DataFrame, codes: set[str]) -> pd.DataFrame:
    if holdings.empty or not codes:
        return holdings.iloc[0:0].copy()
    mask = holdings["基金代码"].astype(str).str.zfill(6).isin(codes)
    return holdings.loc[mask].copy()


def aggregate_stocks(holdings: pd.DataFrame) -> pd.DataFrame:
    if holdings.empty:
        return holdings
    frame = holdings.copy()
    frame["持仓市值"] = pd.to_numeric(frame["持仓市值"], errors="coerce").fillna(0.0)
    frame["占净值比例"] = pd.to_numeric(frame["占净值比例"], errors="coerce")
    stocks = (
        frame.groupby(["股票代码", "股票名称"], as_index=False)
        .agg(
            持有基金数=("基金代码", "nunique"),
            持仓市值_万元=("持仓市值", "sum"),
            平均占净值=("占净值比例", "mean"),
            最高占净值=("占净值比例", "max"),
            全部持股基金数=("披露口径", lambda col: int((col == "全部持股").sum())),
            前十大基金数=("披露口径", lambda col: int((col == "前十大").sum())),
        )
        .sort_values("持仓市值_万元", ascending=False)
        .reset_index(drop=True)
    )
    stocks.insert(0, "序号", range(1, len(stocks) + 1))
    stocks["持仓市值_亿元"] = stocks["持仓市值_万元"] / 10000.0
    return stocks
