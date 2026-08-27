"""Read-only API over the processed 偏股基金池 and holdings."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
UNIVERSE_PATH = PROCESSED / "fund_universe.parquet"
META_PATH = PROCESSED / "fund_universe_meta.json"
HOLDINGS_PATH = PROCESSED / "fund_holdings.parquet"
STOCKS_PATH = PROCESSED / "stocks.parquet"
HOLDINGS_META_PATH = PROCESSED / "holdings_meta.json"

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
