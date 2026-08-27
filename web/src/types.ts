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

export const TYPE_COLORS: Record<string, string> = {
  "混合型-偏股": "#3dcfb6",
  股票型: "#6ea8ff",
  "QDII-混合偏股": "#e0b44a",
  "QDII-普通股票": "#e07a5f",
};
