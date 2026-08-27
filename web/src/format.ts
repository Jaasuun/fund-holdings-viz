export function formatYi(value: number, digits = 1): string {
  return `${value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} 亿`;
}

export function formatPct(value: number, digits = 2): string {
  return `${value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

export function formatSignedPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const pct = Number(value) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`;
}

export function formatQuarter(label: string | null | undefined): string {
  if (!label) return "报告期未知";
  const [year, quarter] = label.split("_");
  const names = ["", "一", "二", "三", "四"];
  const q = Number(quarter);
  return `${year} 年${names[q] ?? quarter}季报`;
}
