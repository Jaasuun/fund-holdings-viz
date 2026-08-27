import type {
  FundsResponse,
  StocksResponse,
  FundHoldingsResponse,
  StockDetail,
  ReturnsBoardResponse,
  FundReturnsResponse,
  TechGapResponse,
  HoldingsPeriodsResponse,
} from "./types";

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `加载失败（${response.status}）`);
  }
  return response.json();
}

function withQuarter(path: string, quarter?: string | null): string {
  if (!quarter) return path;
  const join = path.includes("?") ? "&" : "?";
  return `${path}${join}quarter=${encodeURIComponent(quarter)}`;
}

export function fetchFunds(): Promise<FundsResponse> {
  return readJson("/api/funds");
}

export function fetchHoldingsPeriods(): Promise<HoldingsPeriodsResponse> {
  return readJson("/api/holdings/periods");
}

export function fetchStocks(quarter?: string | null): Promise<StocksResponse> {
  return readJson(withQuarter("/api/stocks", quarter));
}

export function fetchFundHoldings(code: string, quarter?: string | null): Promise<FundHoldingsResponse> {
  return readJson(withQuarter(`/api/funds/${code}/holdings`, quarter));
}

export function fetchStockDetail(code: string, quarter?: string | null): Promise<StockDetail> {
  return readJson(withQuarter(`/api/stocks/${code}`, quarter));
}

export function fetchReturns(): Promise<ReturnsBoardResponse> {
  return readJson("/api/returns");
}

export function fetchFundReturns(code: string): Promise<FundReturnsResponse> {
  return readJson(`/api/funds/${code}/returns`);
}

export function fetchTechGap(): Promise<TechGapResponse> {
  return readJson("/api/returns/tech");
}
