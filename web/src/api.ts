import type {
  FundsResponse,
  StocksResponse,
  FundHoldingsResponse,
  StockDetail,
  ReturnsBoardResponse,
  FundReturnsResponse,
  TechGapResponse,
} from "./types";

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `加载失败（${response.status}）`);
  }
  return response.json();
}

export function fetchFunds(): Promise<FundsResponse> {
  return readJson("/api/funds");
}

export function fetchStocks(): Promise<StocksResponse> {
  return readJson("/api/stocks");
}

export function fetchFundHoldings(code: string): Promise<FundHoldingsResponse> {
  return readJson(`/api/funds/${code}/holdings`);
}

export function fetchStockDetail(code: string): Promise<StockDetail> {
  return readJson(`/api/stocks/${code}`);
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
