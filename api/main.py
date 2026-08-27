"""Read-only API over the processed 偏股基金池 and holdings."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from transform.tech import build_tech_gap

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
UNIVERSE_PATH = PROCESSED / "fund_universe.parquet"
META_PATH = PROCESSED / "fund_universe_meta.json"
HOLDINGS_PATH = PROCESSED / "fund_holdings.parquet"
STOCKS_PATH = PROCESSED / "stocks.parquet"
HOLDINGS_META_PATH = PROCESSED / "holdings_meta.json"
RETURNS_PATH = PROCESSED / "fund_daily_returns.parquet"
BOARD_PATH = PROCESSED / "fund_return_board.parquet"
RETURNS_META_PATH = PROCESSED / "returns_meta.json"

app = FastAPI(title="fund-holdings-viz", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "universe_ready": UNIVERSE_PATH.exists(),
        "holdings_ready": HOLDINGS_PATH.exists(),
        "returns_ready": RETURNS_PATH.exists(),
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
        "funds": frame.to_dict(orient="records"),
    }


@app.get("/api/funds/{code}/holdings")
def fund_holdings(code: str) -> dict:
    if not HOLDINGS_PATH.exists():
        raise HTTPException(status_code=404, detail="尚未生成持仓，请先运行 python -m ingest.holdings")
    code = str(code).zfill(6)
    frame = pd.read_parquet(HOLDINGS_PATH)
    subset = frame[frame["基金代码"].astype(str).str.zfill(6) == code]
    if subset.empty:
        raise HTTPException(status_code=404, detail=f"没有 {code} 的持仓")
    meta = _load_json(HOLDINGS_META_PATH)
    return {
        "fund_code": code,
        "disclosure": subset["披露口径"].iloc[0],
        "report_quarter": meta.get("report_quarter"),
        "count": int(len(subset)),
        "holdings": subset.sort_values("序号").to_dict(orient="records"),
    }


@app.get("/api/stocks")
def list_stocks() -> dict:
    if not STOCKS_PATH.exists():
        raise HTTPException(status_code=404, detail="尚未生成持仓，请先运行 python -m ingest.holdings")
    frame = pd.read_parquet(STOCKS_PATH)
    meta = _load_json(HOLDINGS_META_PATH)
    return {
        "count": int(len(frame)),
        "report_quarter": meta.get("report_quarter"),
        "full_book_funds": meta.get("full_book_funds"),
        "top10_funds": meta.get("top10_funds"),
        "stocks": frame.to_dict(orient="records"),
    }


@app.get("/api/stocks/{code}")
def stock_detail(code: str) -> dict:
    if not HOLDINGS_PATH.exists() or not STOCKS_PATH.exists():
        raise HTTPException(status_code=404, detail="尚未生成持仓，请先运行 python -m ingest.holdings")
    stocks = pd.read_parquet(STOCKS_PATH)
    holdings = pd.read_parquet(HOLDINGS_PATH)
    needle = str(code).strip()
    stock_rows = stocks[stocks["股票代码"].astype(str) == needle]
    if stock_rows.empty and needle.isdigit():
        stock_rows = stocks[stocks["股票代码"].astype(str).str.zfill(6) == needle.zfill(6)]
        needle = needle.zfill(6)
    if stock_rows.empty:
        raise HTTPException(status_code=404, detail=f"没有 {code} 的持股汇总")
    holders = holdings[holdings["股票代码"].astype(str) == str(stock_rows.iloc[0]["股票代码"])]
    holders = holders.sort_values("持仓市值", ascending=False)
    return {
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
    payload = build_tech_gap(daily, universe)
    meta = _load_json(RETURNS_META_PATH)
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
