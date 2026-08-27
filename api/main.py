"""Read-only API over the processed 偏股基金池."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "data" / "processed" / "fund_universe.parquet"
META_PATH = ROOT / "data" / "processed" / "fund_universe_meta.json"

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


def _load_meta() -> dict:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "universe_ready": UNIVERSE_PATH.exists()}


@app.get("/api/funds")
def list_funds() -> dict:
    if not UNIVERSE_PATH.exists():
        raise HTTPException(status_code=404, detail="尚未生成基金池，请先运行 python -m ingest.universe")
    frame = pd.read_parquet(UNIVERSE_PATH)
    meta = _load_meta()
    return {
        "count": int(len(frame)),
        "report_quarter": meta.get("report_quarter"),
        "min_aum_yi": meta.get("min_aum_yi"),
        "funds": frame.to_dict(orient="records"),
    }
