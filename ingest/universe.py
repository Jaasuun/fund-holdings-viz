"""Pull 公募名单 + 季报规模，生成规模超过 50 亿元的偏股产品池。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak
import pandas as pd

from ingest.eastmoney import fetch_fund_scale, latest_report_quarter
from transform.universe import DEFAULT_MIN_AUM_YI, build_universe, write_universe

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def run(min_aum_yi: float = DEFAULT_MIN_AUM_YI, quarter: str | None = None) -> pd.DataFrame:
    quarter = quarter or latest_report_quarter()
    print(f"报告期 {quarter}，拉取基金名单与规模…")

    names = ak.fund_name_em()
    names["基金代码"] = names["基金代码"].astype(str).str.zfill(6)
    scale = fetch_fund_scale(quarter)

    _write_parquet(names, RAW_DIR / "fund_names.parquet")
    _write_parquet(scale, RAW_DIR / "fund_scale.parquet")

    universe = build_universe(names, scale, min_aum_yi=min_aum_yi)
    write_universe(universe, PROCESSED_DIR / "fund_universe.parquet")
    universe.to_json(
        PROCESSED_DIR / "fund_universe.json",
        orient="records",
        force_ascii=False,
        indent=2,
    )
    meta = {
        "report_quarter": quarter,
        "min_aum_yi": min_aum_yi,
        "product_count": int(len(universe)),
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }
    (PROCESSED_DIR / "fund_universe_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"完成：{len(universe)} 只偏股产品（A/C 已合并，规模 > {min_aum_yi:g} 亿元）"
    )
    if not universe.empty:
        preview = universe.head(10)[["序号", "代表代码", "代表简称", "基金类型", "规模_亿元", "份额只数"]]
        print(preview.to_string(index=False))
    return universe


def main() -> None:
    parser = argparse.ArgumentParser(description="接入偏股公募并筛出规模超过 50 亿元的产品")
    parser.add_argument("--min-aum", type=float, default=DEFAULT_MIN_AUM_YI, help="规模下限，单位亿元")
    parser.add_argument("--quarter", default=None, help="报告期，如 2026_2；默认取最新季报")
    args = parser.parse_args()
    run(min_aum_yi=args.min_aum, quarter=args.quarter)


if __name__ == "__main__":
    main()
