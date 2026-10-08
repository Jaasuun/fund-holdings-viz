"""全市场股票类公募：按季报期末净资产拼历史规模走势。"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import akshare as ak
import pandas as pd

from ingest.eastmoney import fetch_fund_scale, latest_report_quarter
from transform.share_class import class_rank, split_share_class
from transform.universe import DEFAULT_MIN_AUM_YI

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
SCALE_CACHE_DIR = RAW_DIR / "fund_scale_quarters"

# 股票类：主动股票 + 股票指数 + 偏股混合 + QDII 股票/偏股
EQUITY_AUM_TYPES = {
    "股票型",
    "指数型-股票",
    "混合型-偏股",
    "QDII-普通股票",
    "QDII-混合偏股",
    "指数型-海外股票",
}

TYPE_ORDER = [
    "混合型-偏股",
    "指数型-股票",
    "股票型",
    "QDII-混合偏股",
    "QDII-普通股票",
    "指数型-海外股票",
]


def _quarter_range(start: str, end: str) -> list[str]:
    sy, sq = (int(part) for part in start.split("_", 1))
    ey, eq = (int(part) for part in end.split("_", 1))
    out: list[str] = []
    year, quarter = sy, sq
    while (year, quarter) <= (ey, eq):
        out.append(f"{year}_{quarter}")
        if quarter == 4:
            year += 1
            quarter = 1
        else:
            quarter += 1
    return out


def _load_or_fetch_scale(quarter: str) -> pd.DataFrame:
    SCALE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = SCALE_CACHE_DIR / f"fund_scale_{quarter}.parquet"
    if cache.is_file():
        frame = pd.read_parquet(cache)
        if not frame.empty:
            return frame
    print(f"  拉取 {quarter} 规模…", flush=True)
    frame = fetch_fund_scale(quarter)
    frame.to_parquet(cache, index=False)
    return frame


def _summarize_quarter(names: pd.DataFrame, scale: pd.DataFrame, quarter: str) -> dict:
    names = names.copy()
    scale = scale.copy()
    names["基金代码"] = names["基金代码"].astype(str).str.zfill(6)
    scale["基金代码"] = scale["基金代码"].astype(str).str.zfill(6)
    equity_names = names[names["基金类型"].isin(EQUITY_AUM_TYPES)][
        ["基金代码", "基金简称", "基金类型"]
    ]
    frame = equity_names.merge(scale, on="基金代码", how="inner", suffixes=("", "_规模"))
    frame["规模_亿元"] = pd.to_numeric(frame["期末净资产_亿元"], errors="coerce").fillna(0.0)
    split = frame["基金简称"].map(split_share_class)
    frame["产品名称"] = split.map(lambda item: item[0])
    frame["份额类别"] = split.map(lambda item: item[1])
    frame["份额优先级"] = frame["份额类别"].map(class_rank)

    by_type = (
        frame.groupby("基金类型", as_index=False)["规模_亿元"]
        .sum()
        .set_index("基金类型")["规模_亿元"]
        .to_dict()
    )
    products = (
        frame.sort_values(["产品名称", "份额优先级", "规模_亿元"], ascending=[True, True, False])
        .groupby("产品名称", as_index=False)
        .agg(规模_亿元=("规模_亿元", "sum"), 基金类型=("基金类型", "first"))
    )
    large = products[products["规模_亿元"] > DEFAULT_MIN_AUM_YI]
    year, q = quarter.split("_", 1)
    return {
        "report_quarter": quarter,
        "label": f"{year}Q{q}",
        "aum_yi": round(float(frame["规模_亿元"].sum()), 2),
        "aum_yi_large": round(float(large["规模_亿元"].sum()), 2),
        "share_count": int(len(frame)),
        "product_count": int(len(products)),
        "large_product_count": int(len(large)),
        "all_scale_count": int(len(scale)),
        "by_type": {key: round(float(by_type.get(key, 0) or 0), 2) for key in TYPE_ORDER},
    }


def run(
    start: str = "2010_1",
    end: str | None = None,
    xueqiu_out: Path | None = None,
) -> dict:
    end = end or latest_report_quarter()
    quarters = _quarter_range(start, end)
    print(f"股票类规模走势 {start} → {end}，共 {len(quarters)} 季", flush=True)

    names = ak.fund_name_em()
    names["基金代码"] = names["基金代码"].astype(str).str.zfill(6)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    names.to_parquet(RAW_DIR / "fund_names.parquet", index=False)

    path = []
    for quarter in quarters:
        scale = _load_or_fetch_scale(quarter)
        row = _summarize_quarter(names, scale, quarter)
        print(
            f"  {row['label']}: {row['aum_yi']:.0f} 亿  "
            f"产品 {row['product_count']}  份额 {row['share_count']}",
            flush=True,
        )
        path.append(row)

    latest = path[-1] if path else {}
    prev = path[-2] if len(path) >= 2 else None
    qoq = None
    if prev and prev.get("aum_yi"):
        qoq = round((latest["aum_yi"] - prev["aum_yi"]) / prev["aum_yi"], 6)
    yoy = None
    if len(path) >= 5 and path[-5].get("aum_yi"):
        yoy = round((latest["aum_yi"] - path[-5]["aum_yi"]) / path[-5]["aum_yi"], 6)

    payload = {
        "start_quarter": start,
        "end_quarter": end,
        "equity_types": TYPE_ORDER,
        "min_aum_yi_large": DEFAULT_MIN_AUM_YI,
        "note": (
            "全市场股票类公募季报期末净资产合计（A/C 份额加总）。"
            "类型含股票型、指数型-股票、混合型-偏股及 QDII 股票/偏股；"
            "按当前基金分类回看历史，已清盘产品不计入。"
        ),
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "latest": {
            **latest,
            "qoq": qoq,
            "yoy": yoy,
        },
        "path": path,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    local_path = PROCESSED_DIR / "equity_aum_trend.json"
    local_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {local_path}")
    if xueqiu_out:
        xueqiu_out = Path(xueqiu_out)
        xueqiu_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, xueqiu_out)
        print(f"已复制 {xueqiu_out}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取全市场股票类公募季报规模走势")
    parser.add_argument("--start", default="2010_1", help="起始报告期，如 2010_1")
    parser.add_argument("--end", default=None, help="结束报告期；默认最新季报")
    parser.add_argument(
        "--xueqiu-out",
        default=str(
            Path.home() / "Desktop" / "xueqiu" / "data" / "fund-holdings" / "processed" / "equity_aum_trend.json"
        ),
        help="同步到雪球 data 目录的路径",
    )
    args = parser.parse_args()
    today = date.today()
    if args.end is None:
        print(f"今天 {today.isoformat()}，自动取最新季报")
    run(start=args.start, end=args.end, xueqiu_out=Path(args.xueqiu_out) if args.xueqiu_out else None)


if __name__ == "__main__":
    main()
