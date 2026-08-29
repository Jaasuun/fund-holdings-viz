"""把日涨幅 / 科技偏离导出为雪球 slim 后端可读的 JSON。"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from ingest.market import fetch_index_daily
from transform.tech import STAR50_SYMBOL, build_tech_gap

ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "data" / "processed"
DAILY_PATH = PROCESSED_DIR / "fund_daily_returns.parquet"
BOARD_PATH = PROCESSED_DIR / "fund_return_board.parquet"
UNIVERSE_PATH = PROCESSED_DIR / "fund_universe.parquet"
META_PATH = PROCESSED_DIR / "returns_meta.json"


def _json_ready(frame: pd.DataFrame) -> list[dict]:
    if frame is None or frame.empty:
        return []
    out = frame.copy()
    for column in out.columns:
        if str(out[column].dtype).startswith("date") or column == "日期":
            out[column] = out[column].astype(str)
    return json.loads(out.to_json(orient="records", force_ascii=False))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def run(out: Path) -> dict:
    if not DAILY_PATH.exists() or not BOARD_PATH.exists() or not UNIVERSE_PATH.exists():
        raise SystemExit("请先运行 python -m ingest.returns")

    daily = pd.read_parquet(DAILY_PATH)
    board = pd.read_parquet(BOARD_PATH)
    universe = pd.read_parquet(UNIVERSE_PATH)
    meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}

    _write_json(out / "fund_daily_returns.json", _json_ready(daily))
    _write_json(out / "fund_return_board.json", _json_ready(board))

    report_end_raw = meta.get("report_end")
    report_end = date.fromisoformat(report_end_raw) if report_end_raw else None
    star50 = pd.DataFrame()
    if report_end is not None:
        try:
            star50 = fetch_index_daily(STAR50_SYMBOL)
        except Exception as exc:  # noqa: BLE001 — 科技偏离图仍可用，只是没有科创50
            print(f"科创50 拉取失败：{exc}")

    payload = build_tech_gap(daily, universe, star50=star50, report_end=report_end)
    tech = {
        "report_quarter": meta.get("report_quarter"),
        "report_end": meta.get("report_end"),
        "fund_count": payload["fund_count"],
        "compared_count": payload["compared_count"],
        "snapshot_date": payload["snapshot_date"],
        "mean_actual": payload["mean_actual"],
        "mean_implied": payload["mean_implied"],
        "mean_gap": payload["mean_gap"],
        "median_gap": payload["median_gap"],
        "star50_latest": payload.get("star50_latest"),
        "path": _json_ready(payload["path"]),
        "funds": _json_ready(payload["funds"]),
    }
    _write_json(out / "tech_gap.json", tech)

    meta = {
        **meta,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_date": payload.get("snapshot_date") or meta.get("asof"),
    }
    _write_json(out / "returns_meta.json", meta)
    print(
        f"已导出到 {out}：日涨幅 {meta.get('day_count')} 日，"
        f"截至 {meta.get('asof') or tech.get('snapshot_date')}"
    )
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="导出雪球公募监测 JSON 快照")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出目录，默认写入本仓库 data/processed",
    )
    args = parser.parse_args()
    out = args.out.expanduser().resolve() if args.out else PROCESSED_DIR
    run(out)


if __name__ == "__main__":
    main()
