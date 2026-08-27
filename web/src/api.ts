import type { FundsResponse } from "./types";

export async function fetchFunds(): Promise<FundsResponse> {
  const response = await fetch("/api/funds");
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `加载失败（${response.status}）`);
  }
  return response.json();
}
