"""Pull complete stock books when 中报/年报 exists, otherwise quarterly top-10."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ingest.eastmoney import fetch_fund_stock_holdings
from transform.holdings import aggregate_stocks, common_fund_codes, filter_to_funds

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
UNIVERSE_PATH = PROCESSED_DIR / "fund_universe.parquet"


def previous_quarter(label: str) -> str:
    year_s, quarter_s = label.split("_")
    year, quarter = int(year_s), int(quarter_s)
    if quarter == 1:
        return f"{year - 1}_4"
    return f"{year}_{quarter - 1}"


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _period_stats(raw: pd.DataFrame, report: str, failures: list[dict]) -> tuple[dict, pd.DataFrame]:
    stocks = aggregate_stocks(raw)
    full_funds = int((raw.groupby("基金代码")["披露口径"].first() == "全部持股").sum())
    top_funds = int((raw.groupby("基金代码")["披露口径"].first() == "前十大").sum())
    meta = {
        "report_quarter": report,
        "fund_count": int(raw["基金代码"].nunique()),
        "full_book_funds": full_funds,
        "top10_funds": top_funds,
        "stock_count": int(len(stocks)),
        "failure_count": len(failures),
    }
    return meta, stocks


def _pull_quarter(universe: pd.DataFrame, report: str) -> tuple[pd.DataFrame, list[dict]]:
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
            failures.append(
                {"基金代码": code, "基金简称": name, "报告期": report, "error": str(exc)}
            )
            print(f"[{n}/{len(universe)}] {code} {name} 失败：{exc}")
            continue
        if holdings.empty:
            failures.append(
                {"基金代码": code, "基金简称": name, "报告期": report, "error": "无持仓表"}
            )
            print(f"[{n}/{len(universe)}] {code} {name} 无持仓")
            continue
        holdings["产品名称"] = row["产品名称"]
        holdings["代表简称"] = name
        parts.append(holdings)
        source = holdings["披露口径"].iloc[0]
        print(f"[{n}/{len(universe)}] {code} {name} {source} {len(holdings)} 只股票")

    if not parts:
        return pd.DataFrame(), failures
    return pd.concat(parts, ignore_index=True), failures


def _load_existing_holdings() -> pd.DataFrame:
    path = PROCESSED_DIR / "fund_holdings.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def run(
    quarters: list[str] | None = None,
    *,
    also_previous: bool = True,
    force: bool = False,
) -> pd.DataFrame:
    if not UNIVERSE_PATH.exists():
        raise SystemExit("尚未生成基金池，请先运行 python -m ingest.universe")

    universe = pd.read_parquet(UNIVERSE_PATH)
    if universe.empty:
        raise SystemExit("基金池为空")

    primary = str(universe["报告期"].iloc[0])
    if quarters:
        labels = list(dict.fromkeys(quarters))
    else:
        labels = [primary]
        if also_previous:
            labels.append(previous_quarter(primary))

    existing = _load_existing_holdings()
    kept_parts: list[pd.DataFrame] = []
    if not existing.empty and "报告期" in existing.columns:
        for report, group in existing.groupby(existing["报告期"].astype(str)):
            if report in labels and not force:
                print(f"报告期 {report} 已有缓存，跳过重拉（可用 --force 强制）")
                kept_parts.append(group)
            elif report not in labels:
                kept_parts.append(group)

    all_parts: list[pd.DataFrame] = list(kept_parts)
    all_failures: list[dict] = []
    period_rows: list[dict] = []
    stocks_by_quarter: dict[str, pd.DataFrame] = {}

    for report in labels:
        if not force and any(
            not part.empty and str(part["报告期"].iloc[0]) == report for part in kept_parts
        ):
            raw = next(part for part in kept_parts if str(part["报告期"].iloc[0]) == report)
            meta, stocks = _period_stats(raw, report, [])
            period_rows.append(meta)
            stocks_by_quarter[report] = stocks
            _write_parquet(stocks, PROCESSED_DIR / f"stocks_{report}.parquet")
            stocks.to_json(
                PROCESSED_DIR / f"stocks_{report}.json",
                orient="records",
                force_ascii=False,
                indent=2,
            )
            continue

        raw, failures = _pull_quarter(universe, report)
        all_failures.extend(failures)
        if raw.empty:
            print(f"报告期 {report} 没有拉到任何持仓，跳过")
            continue
        meta, stocks = _period_stats(raw, report, failures)
        period_rows.append(meta)
        stocks_by_quarter[report] = stocks
        all_parts.append(raw)
        _write_parquet(stocks, PROCESSED_DIR / f"stocks_{report}.parquet")
        stocks.to_json(
            PROCESSED_DIR / f"stocks_{report}.json",
            orient="records",
            force_ascii=False,
            indent=2,
        )
        print(
            f"完成 {report}：{meta['fund_count']} 只基金，全部持股 {meta['full_book_funds']}，"
            f"前十大 {meta['top10_funds']}，股票 {meta['stock_count']} 只，失败 {meta['failure_count']}"
        )

    # Ensure period_rows covers every quarter present in all_parts
    seen = {row["report_quarter"] for row in period_rows}
    for part in all_parts:
        report = str(part["报告期"].iloc[0])
        if report in seen:
            continue
        meta, stocks = _period_stats(part, report, [])
        period_rows.append(meta)
        stocks_by_quarter[report] = stocks
        _write_parquet(stocks, PROCESSED_DIR / f"stocks_{report}.parquet")
        seen.add(report)

    if not all_parts:
        raise SystemExit("没有拉到任何持仓")

    # Dedupe by report period (kept + newly pulled)
    by_report: dict[str, pd.DataFrame] = {}
    for part in all_parts:
        report = str(part["报告期"].iloc[0])
        by_report[report] = part
    combined = pd.concat(list(by_report.values()), ignore_index=True)
    _write_parquet(combined, RAW_DIR / "fund_holdings.parquet")
    _write_parquet(combined, PROCESSED_DIR / "fund_holdings.parquet")

    aligned = common_fund_codes(combined)
    print(
        f"跨期对齐：{len(by_report)} 个报告期，可比基金 {len(aligned)} 只"
        f"（仅保留各期均有持股的产品后再汇总）"
    )

    period_rows = []
    stocks_by_quarter = {}
    for report, raw in by_report.items():
        aligned_raw = filter_to_funds(raw, aligned)
        if aligned_raw.empty:
            print(f"报告期 {report} 对齐后为空，跳过")
            continue
        meta, stocks = _period_stats(aligned_raw, report, [])
        meta["raw_fund_count"] = int(raw["基金代码"].nunique())
        meta["aligned_fund_count"] = int(len(aligned))
        period_rows.append(meta)
        stocks_by_quarter[report] = stocks
        _write_parquet(stocks, PROCESSED_DIR / f"stocks_{report}.parquet")
        stocks.to_json(
            PROCESSED_DIR / f"stocks_{report}.json",
            orient="records",
            force_ascii=False,
            indent=2,
        )
        print(
            f"对齐后 {report}：可比基金 {meta['fund_count']} 只，全部持股 {meta['full_book_funds']}，"
            f"前十大 {meta['top10_funds']}，股票 {meta['stock_count']} 只"
            f"（原始 {meta['raw_fund_count']} 只）"
        )

    if not period_rows:
        raise SystemExit("对齐后没有可用持仓")

    # Sort periods newest first
    def _sort_key(row: dict) -> tuple[int, int]:
        year_s, quarter_s = str(row["report_quarter"]).split("_")
        return int(year_s), int(quarter_s)

    period_rows = sorted(period_rows, key=_sort_key, reverse=True)
    default_meta = next(
        (row for row in period_rows if row["report_quarter"] == primary),
        period_rows[0],
    )
    default_quarter = default_meta["report_quarter"]
    primary_stocks = stocks_by_quarter[default_quarter]
    _write_parquet(primary_stocks, PROCESSED_DIR / "stocks.parquet")
    primary_stocks.to_json(
        PROCESSED_DIR / "stocks.json", orient="records", force_ascii=False, indent=2
    )

    meta = {
        **default_meta,
        "default_quarter": default_quarter,
        "aligned_fund_count": int(len(aligned)),
        "aligned_fund_codes": sorted(aligned),
        "periods": period_rows,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }
    (PROCESSED_DIR / "holdings_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if all_failures:
        (PROCESSED_DIR / "holdings_failures.json").write_text(
            json.dumps(all_failures, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if not primary_stocks.empty:
        print(
            primary_stocks.head(10)[
                ["序号", "股票代码", "股票名称", "持有基金数", "持仓市值_亿元"]
            ].to_string(index=False)
        )
    return primary_stocks


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取偏股基金持股：中报/年报全部，否则季报前十大")
    parser.add_argument(
        "--quarters",
        default="",
        help="逗号分隔报告期，如 2026_2,2026_1；默认用基金池报告期并附带上一季",
    )
    parser.add_argument(
        "--no-previous",
        action="store_true",
        help="仅拉基金池报告期，不附带上一季（一季报）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略已有缓存，强制重拉指定报告期",
    )
    args = parser.parse_args()
    quarters = [part.strip() for part in args.quarters.split(",") if part.strip()] or None
    run(quarters, also_previous=not args.no_previous, force=args.force)


if __name__ == "__main__":
    main()
