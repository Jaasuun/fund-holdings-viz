"""Read-only API over the processed 偏股基金池 and holdings."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.auth_gate import BasicAuthMiddleware, login_status
from ingest.market import fetch_index_daily
from transform.holdings import aggregate_stocks
from transform.tech import STAR50_SYMBOL, build_tech_gap

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
WEB_DIST = ROOT / "web" / "dist"
UNIVERSE_PATH = PROCESSED / "fund_universe.parquet"
META_PATH = PROCESSED / "fund_universe_meta.json"
HOLDINGS_PATH = PROCESSED / "fund_holdings.parquet"
STOCKS_PATH = PROCESSED / "stocks.parquet"
HOLDINGS_META_PATH = PROCESSED / "holdings_meta.json"
RETURNS_PATH = PROCESSED / "fund_daily_returns.parquet"
BOARD_PATH = PROCESSED / "fund_return_board.parquet"
RETURNS_META_PATH = PROCESSED / "returns_meta.json"

app = FastAPI(title="fund-holdings-viz", version="0.1.0")
app.add_middleware(BasicAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _holdings_meta() -> dict:
    return _load_json(HOLDINGS_META_PATH)


def _default_holdings_quarter(meta: dict | None = None) -> str | None:
    meta = meta or _holdings_meta()
    return meta.get("default_quarter") or meta.get("report_quarter")


def _available_holdings_quarters(meta: dict | None = None) -> list[str]:
    meta = meta or _holdings_meta()
    periods = meta.get("periods") or []
    labels = [str(item.get("report_quarter")) for item in periods if item.get("report_quarter")]
    if labels:
        return labels
    if HOLDINGS_PATH.exists():
        frame = pd.read_parquet(HOLDINGS_PATH)
        if "报告期" in frame.columns and not frame.empty:
            return sorted(frame["报告期"].astype(str).unique().tolist(), reverse=True)
    default = _default_holdings_quarter(meta)
    return [default] if default else []


def _period_meta(quarter: str, meta: dict | None = None) -> dict:
    meta = meta or _holdings_meta()
    for item in meta.get("periods") or []:
        if str(item.get("report_quarter")) == quarter:
            return item
    if str(meta.get("report_quarter")) == quarter:
        return meta
    return {"report_quarter": quarter}


def _resolve_holdings_quarter(quarter: str | None) -> str:
    meta = _holdings_meta()
    available = _available_holdings_quarters(meta)
    if not available:
        raise HTTPException(status_code=404, detail="尚未生成持仓，请先运行 python -m ingest.holdings")
    if quarter:
        if quarter not in available:
            raise HTTPException(status_code=404, detail=f"没有报告期 {quarter} 的持仓")
        return quarter
    return _default_holdings_quarter(meta) or available[0]


def _holdings_for_quarter(quarter: str) -> pd.DataFrame:
    if not HOLDINGS_PATH.exists():
        raise HTTPException(status_code=404, detail="尚未生成持仓，请先运行 python -m ingest.holdings")
    frame = pd.read_parquet(HOLDINGS_PATH)
    if "报告期" not in frame.columns:
        return frame
    subset = frame[frame["报告期"].astype(str) == quarter]
    if subset.empty:
        raise HTTPException(status_code=404, detail=f"没有报告期 {quarter} 的持仓")
    return subset


def _stocks_for_quarter(quarter: str) -> pd.DataFrame:
    path = PROCESSED / f"stocks_{quarter}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    if quarter == _default_holdings_quarter() and STOCKS_PATH.exists():
        return pd.read_parquet(STOCKS_PATH)
    holdings = _holdings_for_quarter(quarter)
    return aggregate_stocks(holdings)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "universe_ready": UNIVERSE_PATH.exists(),
        "holdings_ready": HOLDINGS_PATH.exists(),
        "returns_ready": RETURNS_PATH.exists(),
        **login_status(),
    }


@app.get("/api/auth/status")
def auth_status() -> dict:
    return login_status()


@app.get("/api/holdings/periods")
def holdings_periods() -> dict:
    meta = _holdings_meta()
    periods = meta.get("periods") or []
    if not periods:
        for label in _available_holdings_quarters(meta):
            periods.append(_period_meta(label, meta))
    return {
        "default_quarter": _default_holdings_quarter(meta),
        "periods": periods,
    }


@app.get("/api/funds")
def list_funds() -> dict:
    if not UNIVERSE_PATH.exists():
        raise HTTPException(status_code=404, detail="尚未生成基金池，请先运行 python -m ingest.universe")
    frame = pd.read_parquet(UNIVERSE_PATH)
    meta = _load_json(META_PATH)
    return {
        "count": int(len(frame)),
        "report_quarter": meta.get("report_quarter"),
        "min_aum_yi": meta.get("min_aum_yi"),
        "holdings_quarters": _available_holdings_quarters(),
        "default_holdings_quarter": _default_holdings_quarter(),
        "funds": frame.to_dict(orient="records"),
    }


@app.get("/api/funds/{code}/holdings")
def fund_holdings(code: str, quarter: str | None = Query(default=None)) -> dict:
    resolved = _resolve_holdings_quarter(quarter)
    code = str(code).zfill(6)
    frame = _holdings_for_quarter(resolved)
    subset = frame[frame["基金代码"].astype(str).str.zfill(6) == code]
    if subset.empty:
        raise HTTPException(status_code=404, detail=f"没有 {code} 在 {resolved} 的持仓")
    return {
        "fund_code": code,
        "disclosure": subset["披露口径"].iloc[0],
        "report_quarter": resolved,
        "count": int(len(subset)),
        "holdings": subset.sort_values("序号").to_dict(orient="records"),
    }


@app.get("/api/stocks")
def list_stocks(quarter: str | None = Query(default=None)) -> dict:
    resolved = _resolve_holdings_quarter(quarter)
    frame = _stocks_for_quarter(resolved)
    period = _period_meta(resolved)
    return {
        "count": int(len(frame)),
        "report_quarter": resolved,
        "full_book_funds": period.get("full_book_funds"),
        "top10_funds": period.get("top10_funds"),
        "available_quarters": _available_holdings_quarters(),
        "stocks": frame.to_dict(orient="records"),
    }


@app.get("/api/stocks/{code}")
def stock_detail(code: str, quarter: str | None = Query(default=None)) -> dict:
    resolved = _resolve_holdings_quarter(quarter)
    stocks = _stocks_for_quarter(resolved)
    holdings = _holdings_for_quarter(resolved)
    needle = str(code).strip()
    stock_rows = stocks[stocks["股票代码"].astype(str) == needle]
    if stock_rows.empty and needle.isdigit():
        stock_rows = stocks[stocks["股票代码"].astype(str).str.zfill(6) == needle.zfill(6)]
        needle = needle.zfill(6)
    if stock_rows.empty:
        raise HTTPException(status_code=404, detail=f"没有 {code} 在 {resolved} 的持股汇总")
    holders = holdings[holdings["股票代码"].astype(str) == str(stock_rows.iloc[0]["股票代码"])]
    holders = holders.sort_values("持仓市值", ascending=False)
    return {
        "report_quarter": resolved,
        "stock": stock_rows.iloc[0].to_dict(),
        "count": int(len(holders)),
        "holders": holders.to_dict(orient="records"),
    }


def _json_ready(frame: pd.DataFrame) -> list[dict]:
    out = frame.copy()
    for column in out.columns:
        if str(out[column].dtype).startswith("date") or column == "日期":
            out[column] = out[column].astype(str)
    return json.loads(out.to_json(orient="records", force_ascii=False))


@app.get("/api/returns")
def list_returns() -> dict:
    if not BOARD_PATH.exists():
        raise HTTPException(status_code=404, detail="尚未生成日涨幅，请先运行 python -m ingest.returns")
    board = pd.read_parquet(BOARD_PATH)
    meta = _load_json(RETURNS_META_PATH)
    return {
        "count": int(len(board)),
        "report_quarter": meta.get("report_quarter"),
        "report_end": meta.get("report_end"),
        "day_count": meta.get("day_count"),
        "funds": _json_ready(board),
    }


@app.get("/api/returns/tech")
def tech_return_gap() -> dict:
    if not RETURNS_PATH.exists() or not UNIVERSE_PATH.exists():
        raise HTTPException(status_code=404, detail="尚未生成日涨幅，请先运行 python -m ingest.returns")
    daily = pd.read_parquet(RETURNS_PATH)
    universe = pd.read_parquet(UNIVERSE_PATH)
    meta = _load_json(RETURNS_META_PATH)
    report_end_raw = meta.get("report_end")
    report_end = date.fromisoformat(report_end_raw) if report_end_raw else None
    star50 = pd.DataFrame()
    if report_end is not None:
        try:
            star50 = fetch_index_daily(STAR50_SYMBOL)
        except Exception:  # noqa: BLE001 — chart still useful without benchmark
            star50 = pd.DataFrame()
    payload = build_tech_gap(daily, universe, star50=star50, report_end=report_end)
    return {
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
        "path": _json_ready(payload["path"]) if not payload["path"].empty else [],
        "funds": _json_ready(payload["funds"]) if not payload["funds"].empty else [],
    }


@app.get("/api/funds/{code}/returns")
def fund_returns(code: str) -> dict:
    if not RETURNS_PATH.exists():
        raise HTTPException(status_code=404, detail="尚未生成日涨幅，请先运行 python -m ingest.returns")
    code = str(code).zfill(6)
    frame = pd.read_parquet(RETURNS_PATH)
    subset = frame[frame["基金代码"].astype(str).str.zfill(6) == code].sort_values("日期")
    if subset.empty:
        raise HTTPException(status_code=404, detail=f"没有 {code} 的日涨幅")
    meta = _load_json(RETURNS_META_PATH)
    return {
        "fund_code": code,
        "report_quarter": meta.get("report_quarter"),
        "report_end": meta.get("report_end"),
        "count": int(len(subset)),
        "days": _json_ready(subset),
    }


if WEB_DIST.is_dir():
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(
            WEB_DIST / "index.html",
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = WEB_DIST / full_path
        if candidate.is_file() and WEB_DIST in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(
            WEB_DIST / "index.html",
            headers={"Cache-Control": "no-store, max-age=0"},
        )
