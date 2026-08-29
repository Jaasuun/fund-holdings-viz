"""Pull prices + NAV and compute daily fund returns after the report date."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from ingest.market import fetch_a_share_daily, fetch_fund_nav, is_a_share
from transform.returns import implied_daily_returns, latest_return_board, merge_returns, report_end

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
PRICE_DIR = RAW_DIR / "prices"
NAV_DIR = RAW_DIR / "nav"
HOLDINGS_PATH = PROCESSED_DIR / "fund_holdings.parquet"
UNIVERSE_PATH = PROCESSED_DIR / "fund_universe.parquet"


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _load_cached(path: Path) -> pd.DataFrame | None:
    if path.exists():
        return pd.read_parquet(path)
    return None


def _latest_date(frame: pd.DataFrame | None) -> date | None:
    if frame is None or frame.empty or "日期" not in frame.columns:
        return None
    series = pd.to_datetime(frame["日期"], errors="coerce").dropna()
    if series.empty:
        return None
    return series.dt.date.max()


def _is_fresh(latest: date | None, end: date) -> bool:
    if latest is None:
        return False
    if latest >= end:
        return True
    # 周末：周五收盘即可视为最新
    if end.weekday() >= 5:
        friday = end - timedelta(days=end.weekday() - 4)
        return latest >= friday
    return False


def _merge_daily(old: pd.DataFrame | None, new: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if old is None or old.empty:
        return new if new is not None else pd.DataFrame()
    if new is None or new.empty:
        return old
    out = pd.concat([old, new], ignore_index=True)
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce").dt.date
    present = [key for key in keys if key in out.columns]
    if present:
        out = out.drop_duplicates(subset=present, keep="last")
    return out.sort_values("日期").reset_index(drop=True)


def _asof(frame: pd.DataFrame) -> str | None:
    latest = _latest_date(frame)
    return latest.isoformat() if latest else None


def run(*, force: bool = False) -> pd.DataFrame:
    if not HOLDINGS_PATH.exists() or not UNIVERSE_PATH.exists():
        raise SystemExit("请先运行 python -m ingest.universe 与 python -m ingest.holdings")

    holdings = pd.read_parquet(HOLDINGS_PATH)
    universe = pd.read_parquet(UNIVERSE_PATH)
    quarter = str(universe["报告期"].iloc[0])
    start = report_end(quarter)
    price_start = start - timedelta(days=10)
    end = date.today()
    print(f"报告期末 {start} 起计算日涨幅，行情截至 {end}{'（强制重拉）' if force else ''}")

    codes = sorted({str(code) for code in holdings["股票代码"] if is_a_share(str(code))})
    price_parts: list[pd.DataFrame] = []
    price_fail = 0
    price_refresh = 0
    for n, code in enumerate(codes, start=1):
        cache = PRICE_DIR / f"{code}.parquet"
        cached = _load_cached(cache)
        latest = _latest_date(cached)
        if not force and _is_fresh(latest, end):
            if cached is not None and not cached.empty:
                price_parts.append(cached)
            continue
        fetch_start = price_start
        if latest is not None and not force:
            fetch_start = max(price_start, latest - timedelta(days=5))
        try:
            frame = fetch_a_share_daily(code, fetch_start, end, retries=3)
            merged = _merge_daily(cached, frame, ["日期", "股票代码"])
            if merged.empty:
                price_fail += 1
                print(f"[{n}/{len(codes)}] {code} 无行情")
                continue
            _write_parquet(merged, cache)
            price_parts.append(merged)
            price_refresh += 1
            if n % 25 == 0 or n == len(codes):
                print(f"[{n}/{len(codes)}] A股行情已更新 {price_refresh} 只")
        except Exception as exc:  # noqa: BLE001
            price_fail += 1
            if cached is not None and not cached.empty:
                price_parts.append(cached)
                print(f"[{n}/{len(codes)}] {code} 行情失败，沿用缓存：{exc}")
            else:
                _write_parquet(pd.DataFrame(columns=["日期", "收盘", "股票代码"]), cache)
                print(f"[{n}/{len(codes)}] {code} 行情失败：{exc}")

    prices = pd.concat(price_parts, ignore_index=True) if price_parts else pd.DataFrame()
    implied = implied_daily_returns(holdings, prices)

    nav_parts: list[pd.DataFrame] = []
    nav_fail = 0
    nav_refresh = 0
    fund_codes = universe["代表代码"].astype(str).str.zfill(6).tolist()
    for n, code in enumerate(fund_codes, start=1):
        cache = NAV_DIR / f"{code}.parquet"
        cached = _load_cached(cache)
        name = universe.loc[universe["代表代码"].astype(str).str.zfill(6) == code, "代表简称"]
        label = name.iloc[0] if not name.empty else code
        latest = _latest_date(cached)
        if not force and _is_fresh(latest, end) and cached is not None and not cached.empty:
            nav_parts.append(cached)
            continue
        try:
            frame = fetch_fund_nav(code, start, retries=3)
            merged = _merge_daily(cached, frame, ["基金代码", "日期"])
            if merged.empty:
                nav_fail += 1
                print(f"净值 [{n}/{len(fund_codes)}] {code} {label} 无数据")
                continue
            _write_parquet(merged, cache)
            nav_parts.append(merged)
            nav_refresh += 1
            print(f"净值 [{n}/{len(fund_codes)}] {code} {label} {len(merged)} 天")
        except Exception as exc:  # noqa: BLE001
            nav_fail += 1
            if cached is not None and not cached.empty:
                nav_parts.append(cached)
                print(f"净值 [{n}/{len(fund_codes)}] {code} {label} 失败，沿用缓存：{exc}")
            else:
                print(f"净值 [{n}/{len(fund_codes)}] {code} {label} 失败：{exc}")

    nav = pd.concat(nav_parts, ignore_index=True) if nav_parts else pd.DataFrame()
    daily = merge_returns(nav, implied, start)
    names = universe[["代表代码", "产品名称", "代表简称"]].copy()
    names["基金代码"] = names["代表代码"].astype(str).str.zfill(6)
    daily = daily.merge(names[["基金代码", "产品名称", "代表简称"]], on="基金代码", how="left")
    board = latest_return_board(daily, universe)

    _write_parquet(daily, PROCESSED_DIR / "fund_daily_returns.parquet")
    _write_parquet(board, PROCESSED_DIR / "fund_return_board.parquet")
    meta = {
        "report_quarter": quarter,
        "report_end": start.isoformat(),
        "fund_count": int(daily["基金代码"].nunique()) if not daily.empty else 0,
        "day_count": int(daily["日期"].nunique()) if not daily.empty else 0,
        "asof": _asof(daily),
        "price_fail": price_fail,
        "nav_fail": nav_fail,
        "price_refresh": price_refresh,
        "nav_refresh": nav_refresh,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }
    (PROCESSED_DIR / "returns_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"完成：{meta['fund_count']} 只基金，{meta['day_count']} 个交易日，截至 {meta['asof']}；"
        f"行情更新 {price_refresh} 失败 {price_fail}，净值更新 {nav_refresh} 失败 {nav_fail}"
    )
    if not board.empty:
        show = board.head(8)[["序号", "代表简称", "日期", "实际涨幅", "推算涨幅"]]
        print(show.to_string(index=False))
    return board


def main() -> None:
    parser = argparse.ArgumentParser(description="按披露持仓冻结推算日涨幅，并对照基金实际净值")
    parser.add_argument("--force", action="store_true", help="忽略缓存新鲜度，全量重拉")
    args = parser.parse_args()
    run(force=args.force)


if __name__ == "__main__":
    main()
