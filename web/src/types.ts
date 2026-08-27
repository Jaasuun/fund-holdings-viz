export type Fund = {
  序号: number;
  产品名称: string;
  代表代码: string;
  代表简称: string;
  基金类型: string;
  规模_亿元: number;
  份额只数: number;
  份额代码: string;
  是否联接: boolean;
  报告期: string;
};

export type FundsResponse = {
  count: number;
  report_quarter: string | null;
  min_aum_yi: number | null;
  funds: Fund[];
};

export type Holding = {
  序号: number;
  基金代码: string;
  产品名称: string;
  代表简称: string;
  股票代码: string;
  股票名称: string;
  占净值比例: number;
  持股数: number;
  持仓市值: number;
  披露口径: "全部持股" | "前十大";
  报告期: string;
};

export type Stock = {
  序号: number;
  股票代码: string;
  股票名称: string;
  持有基金数: number;
  持仓市值_万元: number;
  持仓市值_亿元: number;
  平均占净值: number;
  最高占净值: number;
  全部持股基金数: number;
  前十大基金数: number;
};

export type StocksResponse = {
  count: number;
  report_quarter: string | null;
  full_book_funds: number | null;
  top10_funds: number | null;
  stocks: Stock[];
};

export type FundHoldingsResponse = {
  fund_code: string;
  disclosure: "全部持股" | "前十大";
  report_quarter: string | null;
  count: number;
  holdings: Holding[];
};

export type StockDetail = {
  stock: Stock;
  count: number;
  holders: Holding[];
};

export type ReturnRow = {
  序号?: number;
  基金代码: string;
  产品名称: string;
  代表简称: string;
  基金类型?: string;
  规模_亿元?: number;
  日期: string;
  单位净值: number | null;
  实际涨幅: number | null;
  推算涨幅: number | null;
  覆盖净值比例: number | null;
  实际累计: number | null;
  推算累计: number | null;
};

export type ReturnsBoardResponse = {
  count: number;
  report_quarter: string | null;
  report_end: string | null;
  day_count: number | null;
  funds: ReturnRow[];
};

export type FundReturnsResponse = {
  fund_code: string;
  report_quarter: string | null;
  report_end: string | null;
  count: number;
  days: ReturnRow[];
};

export const TYPE_COLORS: Record<string, string> = {
  "混合型-偏股": "#0f766e",
  股票型: "#2563eb",
  "QDII-混合偏股": "#d97706",
  "QDII-普通股票": "#dc2626",
};
