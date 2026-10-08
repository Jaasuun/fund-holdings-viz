"""全市场股票类公募：季报净资产 × 净值涨跌 → 日终估算规模（不含申赎）。"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import date, datetime, timezone
from pathlib import Path

import akshare as ak
import pandas as pd
import requests
from akshare.utils import demjson

from ingest.eastmoney import latest_report_quarter
from ingest.scale_history import EQUITY_AUM_TYPES, TYPE_ORDER, _load_or_fetch_scale
from transform.returns import report_end
from transform.share_class import class_rank, split_share_class

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
RANK_CACHE_DIR = RAW_DIR / "aum_rank_custom"
NOTE = (
    "估算规模 = 季报净资产 × 最新净值/报告期末净值（东财开放式排行自定义区间涨跌）；"
    "不含报告期后申赎；已剔除场内 ETF（保留联接基金）。"
    "同一产品多份额按代表份额涨跌套用产品合计规模；"
    "代表份额当日无净值时按季报规模冻结（涨跌记 0）。"
)

_RANK_URL = "https://fund.eastmoney.com/data/rankhandler.aspx"
_RANK_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Referer": "https://fund.eastmoney.com/data/fundranking.html",
}


def _trading_days(start: date, end: date) -> list[date]:
    """Closed interval [start, end] trading days (A-share calendar)."""
    hist = ak.tool_trade_date_hist_sina()
    series = pd.to_datetime(hist["trade_date"]).dt.date
    return [day for day in series.tolist() if start <= day <= end]


def fetch_rank_custom(start: date, end: date, *, force: bool = False) -> pd.DataFrame:
    """东财开放基金排行：自定义区间 [start, end] 涨跌幅（%）。"""
    RANK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = RANK_CACHE_DIR / f"rank_{start.isoformat()}_{end.isoformat()}.parquet"
    if cache.is_file() and not force:
        frame = pd.read_parquet(cache)
        if not frame.empty:
            return frame

    params = {
        "op": "ph",
        "dt": "kf",
        "ft": "all",
        "rs": "",
        "gs": "0",
        "sc": "diy",
        "st": "desc",
        "sd": start.isoformat(),
        "ed": end.isoformat(),
        "qdii": "",
        "tabSubtype": ",,,,,",
        "pi": "1",
        "pn": "30000",
        "dx": "1",
        "v": "0.1",
    }
    last_error: Exception | None = None
    payload: dict | None = None
    for attempt in range(4):
        try:
            response = requests.get(_RANK_URL, params=params, headers=_RANK_HEADERS, timeout=90)
            response.raise_for_status()
            text = response.text
            payload = demjson.decode(text[text.find("{") : -1])
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    if payload is None:
        raise RuntimeError(f"rankhandler failed {start}→{end}") from last_error

    rows: list[dict] = []
    for item in payload.get("datas") or []:
        parts = str(item).split(",")
        if len(parts) < 20:
            continue
        custom_raw = parts[18].strip()
        if custom_raw in {"", "--", "---", "None"}:
            custom = None
        else:
            try:
                custom = float(custom_raw) / 100.0
            except ValueError:
                custom = None
        nav_raw = parts[4].strip()
        try:
            nav = float(nav_raw) if nav_raw not in {"", "--"} else None
        except ValueError:
            nav = None
        rows.append(
            {
                "基金代码": str(parts[0]).zfill(6),
                "日期": parts[3],
                "单位净值": nav,
                "自定义涨跌": custom,
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce").dt.date
        frame.to_parquet(cache, index=False)
    return frame


def _is_exchange_etf(name: str) -> bool:
    """场内 ETF（不含联接）。"""
    text = str(name or "")
    if "联接" in text:
        return False
    return "ETF" in text.upper()


def _build_equity_base(quarter: str) -> pd.DataFrame:
    """产品级底座：场外股票类 × 季报期末净资产（A/C 等份额加总）。"""
    names = ak.fund_name_em()
    names["基金代码"] = names["基金代码"].astype(str).str.zfill(6)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    names.to_parquet(RAW_DIR / "fund_names.parquet", index=False)

    scale = _load_or_fetch_scale(quarter)
    scale = scale.copy()
    scale["基金代码"] = scale["基金代码"].astype(str).str.zfill(6)
    equity = names[names["基金类型"].isin(EQUITY_AUM_TYPES)][
        ["基金代码", "基金简称", "基金类型"]
    ]
    frame = equity.merge(scale, on="基金代码", how="inner", suffixes=("", "_规模"))
    frame["规模_亿元"] = pd.to_numeric(frame["期末净资产_亿元"], errors="coerce").fillna(0.0)
    frame = frame[~frame["基金简称"].map(_is_exchange_etf)].copy()
    split = frame["基金简称"].map(split_share_class)
    frame["产品名称"] = split.map(lambda item: item[0])
    frame["份额类别"] = split.map(lambda item: item[1])
    frame["份额优先级"] = frame["份额类别"].map(class_rank)
    frame = frame[frame["规模_亿元"] > 0].copy()
    # 代表份额优先 A / 无字母，便于对接开放式排行
    products = (
        frame.sort_values(["产品名称", "份额优先级", "规模_亿元"], ascending=[True, True, False])
        .groupby("产品名称", as_index=False)
        .agg(
            代表代码=("基金代码", "first"),
            代表简称=("基金简称", "first"),
            基金类型=("基金类型", "first"),
            规模_亿元=("规模_亿元", "sum"),
            份额只数=("基金代码", "count"),
        )
    )
    return products.reset_index(drop=True)


def _estimate_day(base: pd.DataFrame, rank: pd.DataFrame) -> dict:
    joined = base.merge(
        rank.rename(columns={"基金代码": "代表代码"})[
            ["代表代码", "自定义涨跌", "单位净值", "日期"]
        ],
        on="代表代码",
        how="left",
    )
    # 代表份额不在排行时，尝试同产品任意已入排行的份额涨跌（用规模加权不现实，取首次命中）
    missing = joined["自定义涨跌"].isna()
    if missing.any():
        # 无次级映射时保持缺失；产品级已尽量选 A 类
        pass
    ok = joined["自定义涨跌"].notna()
    joined = joined.copy()
    # 缺净值时冻结季报规模（涨跌按 0），避免合计因漏数断崖
    joined["涨跌填充"] = joined["自定义涨跌"].fillna(0.0)
    joined["估算规模_亿元"] = joined["规模_亿元"] * (1.0 + joined["涨跌填充"])

    by_type_report = (
        joined.groupby("基金类型", as_index=False)["规模_亿元"].sum().set_index("基金类型")["规模_亿元"]
    )
    by_type_est = (
        joined.groupby("基金类型", as_index=False)["估算规模_亿元"]
        .sum()
        .set_index("基金类型")["估算规模_亿元"]
    )
    products_all = int(len(joined))
    products_ok = int(ok.sum())
    aum_report = float(joined["规模_亿元"].sum()) if not joined.empty else 0.0
    aum_est = float(joined["估算规模_亿元"].sum()) if not joined.empty else 0.0
    chg = None
    if aum_report > 0:
        chg = round((aum_est - aum_report) / aum_report, 6)
    nav_date = None
    covered = joined.loc[ok]
    if not covered.empty and covered["日期"].notna().any():
        nav_date = max(day for day in covered["日期"] if day is not None)

    return {
        "aum_yi_report": round(aum_report, 2),
        "aum_yi_est": round(aum_est, 2),
        "chg_vs_report": chg,
        "with_nav": products_ok,
        "nav_fail": products_all - products_ok,
        "share_with_nav": products_ok,
        "share_count": int(joined["份额只数"].sum()) if "份额只数" in joined.columns else products_all,
        "product_count": products_all,
        "nav_date": nav_date.isoformat() if nav_date else None,
        "by_type": {
            key: {
                "aum_yi_report": round(float(by_type_report.get(key, 0) or 0), 2),
                "aum_yi_est": round(float(by_type_est.get(key, 0) or 0), 2),
            }
            for key in TYPE_ORDER
        },
    }


def run(
    *,
    quarter: str | None = None,
    end: date | None = None,
    force: bool = False,
    xueqiu_out: Path | None = None,
) -> dict:
    quarter = quarter or latest_report_quarter()
    start = report_end(quarter)
    end = end or date.today()
    if end < start:
        raise SystemExit(f"结束日 {end} 早于报告期末 {start}")

    print(f"估算规模底座报告期 {quarter}（期末 {start}），净值截至 {end}", flush=True)
    base = _build_equity_base(quarter)
    print(
        f"  场外产品 {len(base)} 只，份额合计 {int(base['份额只数'].sum())}，"
        f"季报净资产 {base['规模_亿元'].sum():.0f} 亿",
        flush=True,
    )

    days = _trading_days(start, end)
    if not days:
        raise SystemExit(f"无交易日：{start} → {end}")

    local_path = PROCESSED_DIR / "equity_aum_estimate.json"
    path: list[dict] = []
    known_dates: set[str] = set()
    if local_path.is_file() and not force:
        try:
            prev = json.loads(local_path.read_text(encoding="utf-8"))
            if prev.get("report_quarter") == quarter and prev.get("report_end") == start.isoformat():
                path = list(prev.get("path") or [])
                known_dates = {str(item.get("date")) for item in path if item.get("date")}
                print(f"  沿用已有路径 {len(path)} 日，增量补齐", flush=True)
        except (json.JSONDecodeError, OSError):
            path = []
            known_dates = set()

    latest_detail: dict | None = None
    todo = [day for day in days if day.isoformat() not in known_dates]
    # 仍要重算最后一日明细（by_type）；若无增量则至少刷新 end 最近交易日
    refresh_days = todo if todo else ([days[-1]] if days else [])
    for idx, day in enumerate(refresh_days, 1):
        # 报告期末当天涨跌为 0，估算=季报底座
        if day == start:
            rank = pd.DataFrame(
                {
                    "基金代码": base["代表代码"],
                    "日期": day,
                    "单位净值": pd.NA,
                    "自定义涨跌": 0.0,
                }
            )
        else:
            rank = fetch_rank_custom(start, day, force=force)
            time.sleep(0.2)
        detail = _estimate_day(base, rank)
        point = {
            "date": day.isoformat(),
            "aum_yi_est": detail["aum_yi_est"],
            "aum_yi_report": detail["aum_yi_report"],
            "with_nav": detail["with_nav"],
            "chg_vs_report": detail["chg_vs_report"],
        }
        if day.isoformat() in known_dates:
            path = [item for item in path if item.get("date") != day.isoformat()]
        path.append(point)
        known_dates.add(day.isoformat())
        latest_detail = detail
        if idx == 1 or idx == len(refresh_days) or idx % 10 == 0:
            print(
                f"  [{idx}/{len(refresh_days)}] {day} 估算 {detail['aum_yi_est']:.0f} 亿 "
                f"覆盖产品 {detail['with_nav']}/{detail['product_count']}",
                flush=True,
            )

    path = sorted(path, key=lambda item: str(item.get("date") or ""))
    if latest_detail is None and path:
        # 仅有历史路径时补算末日 by_type
        last_day = date.fromisoformat(str(path[-1]["date"]))
        if last_day == start:
            rank = pd.DataFrame(
                {
                    "基金代码": base["代表代码"],
                    "日期": last_day,
                    "单位净值": pd.NA,
                    "自定义涨跌": 0.0,
                }
            )
        else:
            rank = fetch_rank_custom(start, last_day, force=force)
        latest_detail = _estimate_day(base, rank)

    assert latest_detail is not None
    aum_report_all = round(float(base["规模_亿元"].sum()), 2)
    payload = {
        "report_quarter": quarter,
        "report_end": start.isoformat(),
        "asof": latest_detail.get("nav_date") or path[-1]["date"],
        "equity_types": TYPE_ORDER,
        "note": NOTE,
        "coverage": {
            "product_count": latest_detail["product_count"],
            "with_nav": latest_detail["with_nav"],
            "nav_fail": latest_detail["nav_fail"],
            "share_count": latest_detail["share_count"],
            "share_with_nav": latest_detail["share_with_nav"],
            "aum_yi_report_all": aum_report_all,
        },
        "latest": {
            "aum_yi_report": latest_detail["aum_yi_report"],
            "aum_yi_est": latest_detail["aum_yi_est"],
            "chg_vs_report": latest_detail["chg_vs_report"],
            "by_type": latest_detail["by_type"],
        },
        "path": path,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    local_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"已写入 {local_path}")
    if xueqiu_out:
        xueqiu_out = Path(xueqiu_out)
        xueqiu_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, xueqiu_out)
        print(f"已复制 {xueqiu_out}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="全市场股票类公募日终估算规模")
    parser.add_argument("--quarter", default=None, help="报告期，如 2026_2；默认最新季报")
    parser.add_argument("--end", default=None, help="净值截止日 YYYY-MM-DD；默认今天")
    parser.add_argument("--force", action="store_true", help="忽略排行缓存重拉")
    parser.add_argument(
        "--xueqiu-out",
        default=None,
        help="同步到雪球 data/fund-holdings/processed/equity_aum_estimate.json",
    )
    args = parser.parse_args()
    end = date.fromisoformat(args.end) if args.end else None
    xueqiu = Path(args.xueqiu_out).expanduser() if args.xueqiu_out else None
    run(quarter=args.quarter, end=end, force=args.force, xueqiu_out=xueqiu)


if __name__ == "__main__":
    main()
