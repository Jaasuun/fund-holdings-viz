"""Pull prices + NAV and compute daily fund returns after the report date."""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _workers(raw: int | None, env_name: str, default: int) -> int:
    if raw is not None:
        return max(1, raw)
    text = (os.getenv(env_name) or "").strip()
    if text.isdigit():
        return max(1, int(text))
    return default


def _tried_recently(path: Path, end: date) -> bool:
    if not path.exists():
        return False
    checked = datetime.fromtimestamp(path.stat().st_mtime).date()
    return _is_fresh(checked, end)


def _empty_price() -> pd.DataFrame:
    return pd.DataFrame(columns=["日期", "收盘", "股票代码"])


def _fetch_price_job(
    code: str, price_start: date, end: date, force: bool
) -> tuple[str, str, pd.DataFrame | None, str | None]:
    cache = PRICE_DIR / f"{code}.parquet"
    cached = _load_cached(cache)
    latest = _latest_date(cached)
    if not force and _is_fresh(latest, end):
        return "cached", code, cached if cached is not None else _empty_price(), None
    if not force and (cached is None or cached.empty) and _tried_recently(cache, end):
        return "skip", code, None, None
    fetch_start = price_start
    if latest is not None and not force:
        fetch_start = max(price_start, latest - timedelta(days=5))
    try:
        frame = fetch_a_share_daily(code, fetch_start, end)
        merged = _merge_daily(cached, frame, ["日期", "股票代码"])
        if merged.empty:
            _write_parquet(_empty_price(), cache)
            return "empty", code, None, None
        _write_parquet(merged, cache)
        return "ok", code, merged, None
    except Exception as exc:  # noqa: BLE001
        if cached is not None and not cached.empty:
            return "fail_cache", code, cached, str(exc)
        return "fail", code, None, str(exc)


def _fetch_nav_job(
    code: str, label: str, start: date, end: date, force: bool
) -> tuple[str, str, str, pd.DataFrame | None, str | None]:
    cache = NAV_DIR / f"{code}.parquet"
    cached = _load_cached(cache)
    latest = _latest_date(cached)
    if not force and _is_fresh(latest, end) and cached is not None and not cached.empty:
        return "cached", code, label, cached, None
    if not force and (cached is None or cached.empty) and _tried_recently(cache, end):
        return "skip", code, label, None, None
    try:
        frame = fetch_fund_nav(code, start)
        merged = _merge_daily(cached, frame, ["基金代码", "日期"])
        if merged.empty:
            return "empty", code, label, None, None
        _write_parquet(merged, cache)
        return "ok", code, label, merged, None
    except Exception as exc:  # noqa: BLE001
        if cached is not None and not cached.empty:
            return "fail_cache", code, label, cached, str(exc)
        return "fail", code, label, None, str(exc)


def run(*, force: bool = False, workers: int | None = None) -> pd.DataFrame:
    if not HOLDINGS_PATH.exists() or not UNIVERSE_PATH.exists():
        raise SystemExit("请先运行 python -m ingest.universe 与 python -m ingest.holdings")

    holdings = pd.read_parquet(HOLDINGS_PATH)
    universe = pd.read_parquet(UNIVERSE_PATH)
    quarter = str(universe["报告期"].iloc[0])
    start = report_end(quarter)
    price_start = start - timedelta(days=10)
    end = date.today()
    price_workers = _workers(workers, "FUND_PRICE_WORKERS", 16)
    nav_workers = _workers(workers, "FUND_NAV_WORKERS", 8)
    print(
        f"报告期末 {start} 起计算日涨幅，行情截至 {end}"
        f"{'（强制重拉）' if force else ''}，行情并发 {price_workers}，净值并发 {nav_workers}"
    )

    codes = sorted({str(code) for code in holdings["股票代码"] if is_a_share(str(code))})
    price_parts: list[pd.DataFrame] = []
    price_fail = 0
    price_refresh = 0
    done = 0
    with ThreadPoolExecutor(max_workers=price_workers) as pool:
        futures = [
            pool.submit(_fetch_price_job, code, price_start, end, force) for code in codes
        ]
        for future in as_completed(futures):
            status, code, frame, error = future.result()
            done += 1
            if status == "ok":
                price_refresh += 1
                price_parts.append(frame)
            elif status in {"cached", "fail_cache"} and frame is not None and not frame.empty:
                if status == "fail_cache":
                    price_fail += 1
                    print(f"[{done}/{len(codes)}] {code} 行情失败，沿用缓存：{error}")
                price_parts.append(frame)
            elif status in {"empty", "fail"}:
                price_fail += 1
                if status == "empty":
                    print(f"[{done}/{len(codes)}] {code} 无行情")
                else:
                    print(f"[{done}/{len(codes)}] {code} 行情失败：{error}")
            if done % 50 == 0 or done == len(codes):
                print(f"[{done}/{len(codes)}] A股行情已处理，新拉 {price_refresh} 只")

    prices = pd.concat(price_parts, ignore_index=True) if price_parts else pd.DataFrame()
    implied = implied_daily_returns(holdings, prices)

    nav_parts: list[pd.DataFrame] = []
    nav_fail = 0
    nav_refresh = 0
    fund_codes = universe["代表代码"].astype(str).str.zfill(6).tolist()
    name_map = {
        str(code).zfill(6): name
        for code, name in zip(
            universe["代表代码"].astype(str), universe["代表简称"].astype(str), strict=False
        )
    }
    done = 0
    with ThreadPoolExecutor(max_workers=nav_workers) as pool:
        futures = [
            pool.submit(_fetch_nav_job, code, name_map.get(code, code), start, end, force)
            for code in fund_codes
        ]
        for future in as_completed(futures):
            status, code, label, frame, error = future.result()
            done += 1
            if status == "ok":
                nav_refresh += 1
                nav_parts.append(frame)
                print(f"净值 [{done}/{len(fund_codes)}] {code} {label} {len(frame)} 天")
            elif status in {"cached", "fail_cache"} and frame is not None and not frame.empty:
                if status == "fail_cache":
                    nav_fail += 1
                    print(f"净值 [{done}/{len(fund_codes)}] {code} {label} 失败，沿用缓存：{error}")
                nav_parts.append(frame)
            elif status in {"empty", "fail"}:
                nav_fail += 1
                reason = "无数据" if status == "empty" else f"失败：{error}"
                print(f"净值 [{done}/{len(fund_codes)}] {code} {label} {reason}")

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
    parser.add_argument("--workers", type=int, default=None, help="行情/净值并发数，默认行情 16、净值 8")
    args = parser.parse_args()
    run(force=args.force, workers=args.workers)


if __name__ == "__main__":
    main()
