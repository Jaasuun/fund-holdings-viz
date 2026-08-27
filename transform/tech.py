"""科技主题基金：实际累计净值 vs 披露持仓推算的差距。"""

from __future__ import annotations

import re

import pandas as pd

TECH_NAME_RE = re.compile(
    r"科技|半导体|人工智能|信息|数字|芯片|集成电路|电子|通信|计算机|互联网"
)


def is_tech_fund(name: str) -> bool:
    return bool(TECH_NAME_RE.search(str(name)))


def tech_universe(universe: pd.DataFrame) -> pd.DataFrame:
    frame = universe.copy()
    frame = frame[frame["产品名称"].map(is_tech_fund)]
    if frame.empty:
        return frame
    return (
        frame.sort_values("规模_亿元", ascending=False)
        .drop_duplicates("产品名称", keep="first")
        .reset_index(drop=True)
    )


def build_tech_gap(daily: pd.DataFrame, universe: pd.DataFrame) -> dict:
    tech = tech_universe(universe)
    codes = set(tech["代表代码"].astype(str).str.zfill(6))
    names = tech[["代表代码", "基金类型", "规模_亿元"]].copy()
    names["基金代码"] = names["代表代码"].astype(str).str.zfill(6)

    subset = daily.copy()
    subset["基金代码"] = subset["基金代码"].astype(str).str.zfill(6)
    subset["日期"] = pd.to_datetime(subset["日期"]).dt.date
    subset = subset[subset["基金代码"].isin(codes)]
    subset = subset.merge(names.drop(columns=["代表代码"]), on="基金代码", how="left")

    both = subset.dropna(subset=["实际累计", "推算累计"]).copy()
    both["差距"] = both["实际累计"] - both["推算累计"]

    path = pd.DataFrame()
    if not both.empty:
        path = (
            both.groupby("日期", as_index=False)
            .agg(
                实际=("实际累计", "mean"),
                推算=("推算累计", "mean"),
                差距=("差距", "mean"),
                基金数=("基金代码", "nunique"),
            )
            .sort_values("日期")
        )

    snapshot_date = both["日期"].max() if not both.empty else None
    snap = both[both["日期"] == snapshot_date].copy() if snapshot_date is not None else both
    if not snap.empty:
        snap = snap.sort_values("差距").reset_index(drop=True)
        snap.insert(0, "序号", range(1, len(snap) + 1))

    return {
        "fund_count": int(len(tech)),
        "compared_count": int(len(snap)),
        "snapshot_date": snapshot_date.isoformat() if snapshot_date else None,
        "mean_actual": float(snap["实际累计"].mean()) if not snap.empty else None,
        "mean_implied": float(snap["推算累计"].mean()) if not snap.empty else None,
        "mean_gap": float(snap["差距"].mean()) if not snap.empty else None,
        "median_gap": float(snap["差距"].median()) if not snap.empty else None,
        "path": path,
        "funds": snap,
    }
