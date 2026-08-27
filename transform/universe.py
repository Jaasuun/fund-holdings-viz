"""Build the local 偏股基金池: merge share classes, keep products above 50亿元."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from transform.share_class import class_rank, split_share_class

EQUITY_TYPES = {
    "股票型",
    "混合型-偏股",
    "QDII-普通股票",
    "QDII-混合偏股",
}

DEFAULT_MIN_AUM_YI = 50.0


def build_universe(
    names: pd.DataFrame,
    scale: pd.DataFrame,
    min_aum_yi: float = DEFAULT_MIN_AUM_YI,
) -> pd.DataFrame:
    names = names.copy()
    scale = scale.copy()
    names["基金代码"] = names["基金代码"].astype(str).str.zfill(6)
    scale["基金代码"] = scale["基金代码"].astype(str).str.zfill(6)

    equity = names[names["基金类型"].isin(EQUITY_TYPES)].copy()
    frame = equity.merge(scale, on="基金代码", how="inner", suffixes=("", "_规模"))
    if "基金简称_规模" in frame.columns:
        frame["基金简称"] = frame["基金简称"].fillna(frame["基金简称_规模"])

    split = frame["基金简称"].map(split_share_class)
    frame["产品名称"] = split.map(lambda item: item[0])
    frame["份额类别"] = split.map(lambda item: item[1])
    frame["是否联接"] = frame["基金简称"].str.contains("联接", na=False)
    frame["规模_亿元"] = pd.to_numeric(frame["期末净资产_亿元"], errors="coerce").fillna(0.0)
    frame["份额优先级"] = frame["份额类别"].map(class_rank)

    products = (
        frame.sort_values(["产品名称", "份额优先级", "规模_亿元"], ascending=[True, True, False])
        .groupby("产品名称", as_index=False)
        .agg(
            代表代码=("基金代码", "first"),
            代表简称=("基金简称", "first"),
            基金类型=("基金类型", "first"),
            规模_亿元=("规模_亿元", "sum"),
            份额只数=("基金代码", "count"),
            份额代码=("基金代码", lambda codes: ",".join(codes)),
            是否联接=("是否联接", "any"),
            报告期=("报告期", "first"),
        )
    )
    products = products[products["规模_亿元"] > min_aum_yi].copy()
    products = products.sort_values("规模_亿元", ascending=False).reset_index(drop=True)
    products.insert(0, "序号", range(1, len(products) + 1))
    return products


def write_universe(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path
