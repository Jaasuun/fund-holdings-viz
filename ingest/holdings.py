"""Pull complete stock books when 中报/年报 exists, otherwise quarterly top-10."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ingest.eastmoney import fetch_fund_stock_holdings
from transform.holdings import aggregate_stocks

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
UNIVERSE_PATH = PROCESSED_DIR / "fund_universe.parquet"


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def run() -> pd.DataFrame:
    if not UNIVERSE_PATH.exists():
        raise SystemExit("尚未生成基金池，请先运行 python -m ingest.universe")

    universe = pd.read_parquet(UNIVERSE_PATH)
    if universe.empty:
        raise SystemExit("基金池为空")

    report = str(universe["报告期"].iloc[0])
    year_s, quarter_s = report.split("_")
    year, quarter = int(year_s), int(quarter_s)
    print(f"报告期 {report}：优先全部持股，没有则前十大。共 {len(universe)} 只产品。")

    parts: list[pd.DataFrame] = []
    failures: list[dict] = []
    for n, (_, row) in enumerate(universe.iterrows(), start=1):
        code = str(row["代表代码"]).zfill(6)
        name = row["代表简称"]
        try:
            holdings = fetch_fund_stock_holdings(code, year, quarter)
        except Exception as exc:  # noqa: BLE001
            failures.append({"基金代码": code, "基金简称": name, "error": str(exc)})
            print(f"[{n}/{len(universe)}] {code} {name} 失败：{exc}")
            continue
        if holdings.empty:
            failures.append({"基金代码": code, "基金简称": name, "error": "无持仓表"})
            print(f"[{n}/{len(universe)}] {code} {name} 无持仓")
            continue
        holdings["产品名称"] = row["产品名称"]
        holdings["代表简称"] = name
        parts.append(holdings)
        source = holdings["披露口径"].iloc[0]
        print(f"[{n}/{len(universe)}] {code} {name} {source} {len(holdings)} 只股票")

    if not parts:
        raise SystemExit("没有拉到任何持仓")

    raw = pd.concat(parts, ignore_index=True)
    _write_parquet(raw, RAW_DIR / "fund_holdings.parquet")

    stocks = aggregate_stocks(raw)
    _write_parquet(raw, PROCESSED_DIR / "fund_holdings.parquet")
    _write_parquet(stocks, PROCESSED_DIR / "stocks.parquet")
    stocks.to_json(PROCESSED_DIR / "stocks.json", orient="records", force_ascii=False, indent=2)

    full_funds = int((raw.groupby("基金代码")["披露口径"].first() == "全部持股").sum())
    top_funds = int((raw.groupby("基金代码")["披露口径"].first() == "前十大").sum())
    meta = {
        "report_quarter": report,
        "fund_count": int(raw["基金代码"].nunique()),
        "full_book_funds": full_funds,
        "top10_funds": top_funds,
        "stock_count": int(len(stocks)),
        "failure_count": len(failures),
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }
    (PROCESSED_DIR / "holdings_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if failures:
        (PROCESSED_DIR / "holdings_failures.json").write_text(
            json.dumps(failures, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(
        f"完成：{meta['fund_count']} 只基金，全部持股 {full_funds}，前十大 {top_funds}，"
        f"股票 {meta['stock_count']} 只，失败 {len(failures)}"
    )
    if not stocks.empty:
        print(stocks.head(10)[["序号", "股票代码", "股票名称", "持有基金数", "持仓市值_亿元"]].to_string(index=False))
    return stocks


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取偏股基金持股：中报/年报全部，否则季报前十大")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
