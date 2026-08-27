import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchFundHoldings, fetchFundReturns, fetchFunds, fetchHoldingsPeriods, fetchReturns, fetchStockDetail, fetchStocks, fetchTechGap } from "./api";
import { formatPct, formatQuarter, formatSignedPct, formatYi } from "./format";
import {
  TYPE_COLORS,
  type Fund,
  type FundHoldingsResponse,
  type FundReturnsResponse,
  type FundsResponse,
  type ReturnRow,
  type ReturnsBoardResponse,
  type Stock,
  type StockDetail,
  type StocksResponse,
  type TechGapResponse,
} from "./types";

const CHART_TICK = { fill: "#6b7280", fontSize: 12 };
const CHART_AXIS = { fill: "#111827", fontSize: 12 };
const TOOLTIP_STYLE = {
  background: "#ffffff",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  color: "#111827",
};

const BUCKETS = [
  { key: "50–80 亿", test: (v: number) => v <= 80 },
  { key: "80–120 亿", test: (v: number) => v > 80 && v <= 120 },
  { key: "120–200 亿", test: (v: number) => v > 120 && v <= 200 },
  { key: "200 亿以上", test: (v: number) => v > 200 },
];

function chgClass(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "chg";
  if (Number(value) > 0) return "chg pos";
  if (Number(value) < 0) return "chg neg";
  return "chg";
}

const TECH_LINES = [
  { key: "实际", color: "#2563eb" },
  { key: "推算", color: "#0f766e" },
  { key: "科创50", color: "#7c3aed" },
  { key: "差距", color: "#b45309" },
  { key: "差额", color: "#db2777" },
] as const;

const RETURN_LINES = [
  { key: "实际", color: "#2563eb" },
  { key: "推算", color: "#0f766e" },
] as const;

export default function App() {
  const [data, setData] = useState<FundsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("全部");
  const [selected, setSelected] = useState<Fund | null>(null);
  const [view, setView] = useState<"funds" | "stocks" | "returns" | "tech">("tech");
  const [stocks, setStocks] = useState<StocksResponse | null>(null);
  const [stocksError, setStocksError] = useState<string | null>(null);
  const [holdingsQuarter, setHoldingsQuarter] = useState<string | null>(null);
  const [holdingsQuarters, setHoldingsQuarters] = useState<string[]>([]);
  const [stockQuery, setStockQuery] = useState("");
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [fundHoldings, setFundHoldings] = useState<FundHoldingsResponse | null>(null);
  const [stockDetail, setStockDetail] = useState<StockDetail | null>(null);
  const [returns, setReturns] = useState<ReturnsBoardResponse | null>(null);
  const [returnsError, setReturnsError] = useState<string | null>(null);
  const [returnQuery, setReturnQuery] = useState("");
  const [selectedReturn, setSelectedReturn] = useState<ReturnRow | null>(null);
  const [fundReturns, setFundReturns] = useState<FundReturnsResponse | null>(null);
  const [tech, setTech] = useState<TechGapResponse | null>(null);
  const [techError, setTechError] = useState<string | null>(null);
  const [techQuery, setTechQuery] = useState("");
  const [selectedTech, setSelectedTech] = useState<ReturnRow | null>(null);
  const [techHidden, setTechHidden] = useState<Record<string, boolean>>({});
  const [returnHidden, setReturnHidden] = useState<Record<string, boolean>>({});

  const toggleTechLine = (key: string) => {
    setTechHidden((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleReturnLine = (key: string) => {
    setReturnHidden((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  useEffect(() => {
    fetchFunds()
      .then(setData)
      .catch((err: Error) => setError(err.message));
    fetchHoldingsPeriods()
      .then((payload) => {
        const labels = payload.periods.map((item) => item.report_quarter).filter(Boolean);
        setHoldingsQuarters(labels);
        setHoldingsQuarter((current) => current ?? payload.default_quarter ?? labels[0] ?? null);
      })
      .catch(() => {
        /* stocks fetch still works for single-period caches */
      });
    fetchReturns()
      .then(setReturns)
      .catch((err: Error) => setReturnsError(err.message));
    fetchTechGap()
      .then(setTech)
      .catch((err: Error) => setTechError(err.message));
  }, []);

  useEffect(() => {
    setStocks(null);
    setStocksError(null);
    setSelectedStock(null);
    fetchStocks(holdingsQuarter)
      .then((payload) => {
        setStocks(payload);
        if (payload.available_quarters?.length) {
          setHoldingsQuarters(payload.available_quarters);
        }
        if (!holdingsQuarter && payload.report_quarter) {
          setHoldingsQuarter(payload.report_quarter);
        }
      })
      .catch((err: Error) => setStocksError(err.message));
  }, [holdingsQuarter]);

  useEffect(() => {
    if (!selected) {
      setFundHoldings(null);
      return;
    }
    fetchFundHoldings(selected.代表代码, holdingsQuarter)
      .then(setFundHoldings)
      .catch(() => setFundHoldings(null));
  }, [selected, holdingsQuarter]);

  useEffect(() => {
    if (!selectedStock) {
      setStockDetail(null);
      return;
    }
    fetchStockDetail(selectedStock.股票代码, holdingsQuarter)
      .then(setStockDetail)
      .catch(() => setStockDetail(null));
  }, [selectedStock, holdingsQuarter]);

  useEffect(() => {
    if (!selectedReturn) {
      setFundReturns(null);
      return;
    }
    fetchFundReturns(selectedReturn.基金代码)
      .then(setFundReturns)
      .catch(() => setFundReturns(null));
  }, [selectedReturn]);

  useEffect(() => {
    if (!selectedTech) {
      return;
    }
    fetchFundReturns(selectedTech.基金代码)
      .then(setFundReturns)
      .catch(() => setFundReturns(null));
  }, [selectedTech]);

  const funds = data?.funds ?? [];
  const types = useMemo(
    () => ["全部", ...Array.from(new Set(funds.map((item) => item.基金类型)))],
    [funds],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return funds.filter((item) => {
      const typeOk = type === "全部" || item.基金类型 === type;
      const text = `${item.产品名称}${item.代表简称}${item.代表代码}${item.份额代码}`.toLowerCase();
      return typeOk && (!q || text.includes(q));
    });
  }, [funds, query, type]);

  const kpis = useMemo(() => {
    const total = funds.reduce((sum, item) => sum + item.规模_亿元, 0);
    const avg = funds.length ? total / funds.length : 0;
    const top = funds[0];
    return { total, avg, top };
  }, [funds]);

  const typeChart = useMemo(() => {
    const counts = new Map<string, { count: number; aum: number }>();
    for (const item of funds) {
      const current = counts.get(item.基金类型) ?? { count: 0, aum: 0 };
      current.count += 1;
      current.aum += item.规模_亿元;
      counts.set(item.基金类型, current);
    }
    return [...counts.entries()].map(([name, value]) => ({
      name,
      value: value.count,
      aum: value.aum,
    }));
  }, [funds]);

  const buckets = useMemo(
    () =>
      BUCKETS.map((bucket) => ({
        name: bucket.key,
        value: funds.filter((item) => bucket.test(item.规模_亿元)).length,
      })),
    [funds],
  );

  const topBars = useMemo(
    () =>
      [...filtered]
        .sort((a, b) => b.规模_亿元 - a.规模_亿元)
        .slice(0, 12)
        .map((item) => ({
          name: item.产品名称.length > 12 ? `${item.产品名称.slice(0, 12)}…` : item.产品名称,
          full: item.产品名称,
          aum: Number(item.规模_亿元.toFixed(1)),
          type: item.基金类型,
        }))
        .reverse(),
    [filtered],
  );

  const filteredStocks = useMemo(() => {
    const q = stockQuery.trim().toLowerCase();
    const list = stocks?.stocks ?? [];
    if (!q) return list;
    return list.filter((item) =>
      `${item.股票名称}${item.股票代码}`.toLowerCase().includes(q),
    );
  }, [stocks, stockQuery]);

  const stockBars = useMemo(
    () =>
      [...filteredStocks]
        .slice(0, 12)
        .map((item) => ({
          name: item.股票名称,
          aum: Number(item.持仓市值_亿元.toFixed(2)),
        }))
        .reverse(),
    [filteredStocks],
  );

  const filteredReturns = useMemo(() => {
    const q = returnQuery.trim().toLowerCase();
    const list = returns?.funds ?? [];
    if (!q) return list;
    return list.filter((item) =>
      `${item.产品名称 ?? ""}${item.代表简称 ?? ""}${item.基金代码}`.toLowerCase().includes(q),
    );
  }, [returns, returnQuery]);

  const returnChart = useMemo(
    () =>
      (fundReturns?.days ?? []).map((item) => ({
        date: String(item.日期).slice(5),
        实际: item.实际累计 == null ? null : Number(item.实际累计) * 100,
        推算: item.推算累计 == null ? null : Number(item.推算累计) * 100,
      })),
    [fundReturns],
  );

  const techPath = useMemo(
    () =>
      (tech?.path ?? []).map((item) => ({
        date: String(item.日期).slice(5),
        实际: Number(item.实际) * 100,
        推算: Number(item.推算) * 100,
        差距: Number(item.差距) * 100,
        差额: item.差额 == null ? null : Number(item.差额) * 100,
        科创50: item.科创50 == null ? null : Number(item.科创50) * 100,
      })),
    [tech],
  );

  const techBars = useMemo(
    () =>
      [...(tech?.funds ?? [])]
        .sort((a, b) => Number(a.差距 ?? 0) - Number(b.差距 ?? 0))
        .map((item) => ({
          name: (item.产品名称 ?? item.代表简称 ?? "").slice(0, 10),
          full: item.产品名称,
          gap: Number(item.差距 ?? 0) * 100,
        })),
    [tech],
  );

  const filteredTech = useMemo(() => {
    const q = techQuery.trim().toLowerCase();
    const list = tech?.funds ?? [];
    if (!q) return list;
    return list.filter((item) =>
      `${item.产品名称 ?? ""}${item.代表简称 ?? ""}${item.基金代码}`.toLowerCase().includes(q),
    );
  }, [tech, techQuery]);

  if (error) {
    return (
      <div className="app">
        <p className="status error">{error}。请先运行 python -m ingest.universe，并启动 API。</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="app">
        <p className="status">正在读取基金池…</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="hero">
        <div>
          <p className="eyebrow">Fund Holdings Viz</p>
          <h1>规模超过 50 亿元的偏股公募</h1>
          <p className="lede">
            A/C 等份额已按主基金合并。科技页比较披露持仓推算累计与实际净值累计的差距。
          </p>
        </div>
        <div className="badge">{formatQuarter(data.report_quarter)}</div>
      </header>

      <nav className="tabs">
        <button className={view === "tech" ? "tab active" : "tab"} type="button" onClick={() => setView("tech")}>
          科技偏离
        </button>
        <button className={view === "returns" ? "tab active" : "tab"} type="button" onClick={() => setView("returns")}>
          日涨幅
        </button>
        <button className={view === "stocks" ? "tab active" : "tab"} type="button" onClick={() => setView("stocks")}>
          持股排行
        </button>
        <button className={view === "funds" ? "tab active" : "tab"} type="button" onClick={() => setView("funds")}>
          基金池
        </button>
      </nav>

      {view === "tech" ? (
        <>
          <section className="kpis">
            <article className="card kpi">
              <span>科技主题产品</span>
              <strong>{tech?.fund_count ?? "—"}</strong>
            </article>
            <article className="card kpi">
              <span>等权实际累计</span>
              <strong className={chgClass(tech?.mean_actual)}>{formatSignedPct(tech?.mean_actual)}</strong>
            </article>
            <article className="card kpi">
              <span>等权差距 实际−推算</span>
              <strong className={chgClass(tech?.mean_gap)}>{formatSignedPct(tech?.mean_gap)}</strong>
            </article>
            <article className="card kpi">
              <span>科创50累计</span>
              <strong className={chgClass(tech?.star50_latest)}>{formatSignedPct(tech?.star50_latest)}</strong>
            </article>
          </section>
          {techError ? (
            <p className="status error">{techError}。请先运行 python -m ingest.returns。</p>
          ) : null}
          {tech ? (
            <>
              <section className="card panel">
                <h2>科技基金等权累计</h2>
                <p>
                  报告期末后，科技主题基金等权平均，并对照科创50。差距 = 累计实际 − 累计推算；差额 = 当日实际涨幅 − 当日推算涨幅。点击图例可隐藏或显示对应曲线。
                </p>
                <div className="chart" style={{ height: 320 }}>
                  <ResponsiveContainer>
                    <LineChart data={techPath} margin={{ left: 8, right: 16 }}>
                      <CartesianGrid stroke="#eef0f3" />
                      <XAxis dataKey="date" tick={CHART_TICK} axisLine={false} tickLine={false} />
                      <YAxis tick={CHART_TICK} axisLine={false} tickLine={false} unit="%" />
                      <Tooltip
                        formatter={(value) => [`${Number(value).toFixed(2)}%`, ""]}
                        contentStyle={TOOLTIP_STYLE}
                      />
                      <Legend
                        wrapperStyle={{ cursor: "pointer" }}
                        onClick={(entry) => {
                          const key = String(entry.dataKey ?? entry.value ?? "");
                          if (key) toggleTechLine(key);
                        }}
                      />
                      {TECH_LINES.map((line) => (
                        <Line
                          key={line.key}
                          type="monotone"
                          dataKey={line.key}
                          stroke={line.color}
                          dot={false}
                          strokeWidth={2}
                          hide={Boolean(techHidden[line.key])}
                          connectNulls
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </section>
              <section className="card panel" style={{ marginTop: 14 }}>
                <h2>个基差距 实际−推算</h2>
                <p>越往左（红）实际越差于冻结持仓，越往右（绿）实际越好于季报持仓。</p>
                <div className="chart" style={{ height: 640 }}>
                  <ResponsiveContainer>
                    <BarChart data={techBars} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <CartesianGrid stroke="#eef0f3" horizontal={false} />
                      <XAxis type="number" tick={CHART_TICK} axisLine={false} tickLine={false} unit="%" />
                      <YAxis type="category" dataKey="name" width={108} tick={CHART_AXIS} axisLine={false} tickLine={false} />
                      <Tooltip
                        formatter={(value) => [`${Number(value).toFixed(2)}%`, "差距"]}
                        labelFormatter={(_, payload) => String(payload?.[0]?.payload.full ?? "")}
                        contentStyle={TOOLTIP_STYLE}
                      />
                      <Bar dataKey="gap" radius={[0, 8, 8, 0]}>
                        {techBars.map((item) => (
                          <Cell key={item.full} fill={item.gap >= 0 ? "#15803d" : "#b91c1c"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
              <section className="card table-wrap" style={{ marginTop: 14 }}>
                <h2>科技基金累计差距</h2>
                <p>
                  {filteredTech.length} 只可对比。名称含科技 / 半导体 / 人工智能 / 信息 / 数字等；同产品多份额已去重。
                </p>
                <div className="toolbar">
                  <input
                    className="search"
                    value={techQuery}
                    placeholder="搜索基金名称 / 代码"
                    onChange={(event) => setTechQuery(event.target.value)}
                  />
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>基金</th>
                      <th className="num">实际累计</th>
                      <th className="num">推算累计</th>
                      <th className="num">差距</th>
                      <th className="num">覆盖净值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTech.map((item) => (
                      <tr
                        key={item.基金代码}
                        onClick={() => {
                          setSelectedTech(item);
                          setSelectedReturn(item);
                          setView("returns");
                        }}
                      >
                        <td>{item.序号}</td>
                        <td>
                          <div>{item.产品名称}</div>
                          <div className="type-pill">
                            {item.基金代码} · {item.代表简称}
                          </div>
                        </td>
                        <td className={`num ${chgClass(item.实际累计)}`}>{formatSignedPct(item.实际累计)}</td>
                        <td className={`num ${chgClass(item.推算累计)}`}>{formatSignedPct(item.推算累计)}</td>
                        <td className={`num ${chgClass(item.差距)}`}>{formatSignedPct(item.差距)}</td>
                        <td className="num">{item.覆盖净值比例 == null ? "—" : formatPct(item.覆盖净值比例 * 100, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          ) : !techError ? (
            <p className="status">正在计算科技偏离…</p>
          ) : null}
        </>
      ) : null}

      {view === "returns" ? (
        <>
          <section className="kpis">
            <article className="card kpi">
              <span>有涨幅的基金</span>
              <strong>{returns?.count ?? "—"}</strong>
            </article>
            <article className="card kpi">
              <span>交易日</span>
              <strong>{returns?.day_count ?? "—"}</strong>
            </article>
            <article className="card kpi">
              <span>最新一日领涨</span>
              <strong className={chgClass(returns?.funds[0]?.实际涨幅)}>
                {returns?.funds[0] ? formatSignedPct(returns.funds[0].实际涨幅) : "—"}
              </strong>
            </article>
            <article className="card kpi">
              <span>报告期末</span>
              <strong style={{ fontSize: 20 }}>{returns?.report_end ?? "—"}</strong>
            </article>
          </section>
          {returnsError ? (
            <p className="status error">{returnsError}。请先运行 python -m ingest.returns。</p>
          ) : null}
          {returns ? (
            <>
              <section className="card panel">
                <h2>{selectedReturn ? `${selectedReturn.代表简称} 累计涨幅` : "点选基金查看累计曲线"}</h2>
                <p>实际净值来自基金公布的日增长率；推算按披露持仓权重和 A 股后复权行情，现金及其他资产按 0。</p>
                <div className="chart" style={{ height: 320 }}>
                  {returnChart.length ? (
                    <ResponsiveContainer>
                      <LineChart data={returnChart} margin={{ left: 8, right: 16 }}>
                        <CartesianGrid stroke="#eef0f3" />
                        <XAxis dataKey="date" tick={CHART_TICK} axisLine={false} tickLine={false} />
                        <YAxis tick={CHART_TICK} axisLine={false} tickLine={false} unit="%" />
                        <Tooltip
                          formatter={(value) => [`${Number(value).toFixed(2)}%`, ""]}
                          contentStyle={TOOLTIP_STYLE}
                        />
                        <Legend
                          wrapperStyle={{ cursor: "pointer" }}
                          onClick={(entry) => {
                            const key = String(entry.dataKey ?? entry.value ?? "");
                            if (key) toggleReturnLine(key);
                          }}
                        />
                        {RETURN_LINES.map((line) => (
                          <Line
                            key={line.key}
                            type="monotone"
                            dataKey={line.key}
                            stroke={line.color}
                            dot={false}
                            strokeWidth={2}
                            hide={Boolean(returnHidden[line.key])}
                            connectNulls
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="status">选择下面表格中的一只基金。</p>
                  )}
                </div>
              </section>
              <section className="card table-wrap" style={{ marginTop: 14 }}>
                <h2>最新一日涨幅</h2>
                <p>
                  {filteredReturns.length} / {returns.count} 只。实际为基金净值日涨幅，推算为披露持仓组合日涨幅。
                </p>
                <div className="toolbar">
                  <input
                    className="search"
                    value={returnQuery}
                    placeholder="搜索基金名称 / 代码"
                    onChange={(event) => setReturnQuery(event.target.value)}
                  />
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>基金</th>
                      <th>日期</th>
                      <th className="num">实际日涨幅</th>
                      <th className="num">持仓推算</th>
                      <th className="num">实际累计</th>
                      <th className="num">覆盖净值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredReturns.map((item) => (
                      <tr key={item.基金代码} onClick={() => setSelectedReturn(item)}>
                        <td>{item.序号}</td>
                        <td>
                          <div>{item.产品名称}</div>
                          <div className="type-pill">
                            {item.基金代码} · {item.代表简称}
                          </div>
                        </td>
                        <td>{item.日期}</td>
                        <td className={`num ${chgClass(item.实际涨幅)}`}>{formatSignedPct(item.实际涨幅)}</td>
                        <td className={`num ${chgClass(item.推算涨幅)}`}>{formatSignedPct(item.推算涨幅)}</td>
                        <td className={`num ${chgClass(item.实际累计)}`}>{formatSignedPct(item.实际累计)}</td>
                        <td className="num">{item.覆盖净值比例 == null ? "—" : formatPct(item.覆盖净值比例 * 100, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          ) : !returnsError ? (
            <p className="status">正在读取日涨幅…</p>
          ) : null}
        </>
      ) : null}

      {view === "stocks" ? (
        <>
          {holdingsQuarters.length > 1 ? (
            <div className="period-bar">
              <span className="period-label">持股报告期</span>
              <div className="period-tabs">
                {holdingsQuarters.map((label) => (
                  <button
                    key={label}
                    type="button"
                    className={holdingsQuarter === label ? "period-tab active" : "period-tab"}
                    onClick={() => setHoldingsQuarter(label)}
                  >
                    {formatQuarter(label)}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <section className="kpis">
            <article className="card kpi">
              <span>覆盖股票</span>
              <strong>{stocks?.count ?? "—"}</strong>
            </article>
            <article className="card kpi">
              <span>全部持股基金</span>
              <strong>{stocks?.full_book_funds ?? "—"}</strong>
            </article>
            <article className="card kpi">
              <span>仅前十大基金</span>
              <strong>{stocks?.top10_funds ?? "—"}</strong>
            </article>
            <article className="card kpi">
              <span>第一大重仓</span>
              <strong>{stocks?.stocks[0] ? formatYi(stocks.stocks[0].持仓市值_亿元, 1) : "—"}</strong>
            </article>
          </section>
          {stocksError ? (
            <p className="status error">{stocksError}。请先运行 python -m ingest.holdings。</p>
          ) : null}
          {stocks ? (
            <>
              <section className="card panel">
                <h2>持仓市值排行 · {formatQuarter(stocks.report_quarter)}</h2>
                <p>
                  {stocks.report_quarter?.endsWith("_1") || stocks.report_quarter?.endsWith("_3")
                    ? "一/三季报仅披露前十大重仓，按前十大市值合计排行。"
                    : "池内基金持有市值合计，前 12 名。有中报/年报的基金按全部持股计入，其余按前十大。"}
                </p>
                <div className="chart" style={{ height: 420 }}>
                  <ResponsiveContainer>
                    <BarChart data={stockBars} layout="vertical" margin={{ left: 16, right: 16 }}>
                      <CartesianGrid stroke="#eef0f3" horizontal={false} />
                      <XAxis type="number" tick={CHART_TICK} axisLine={false} tickLine={false} />
                      <YAxis type="category" dataKey="name" width={88} tick={CHART_AXIS} axisLine={false} tickLine={false} />
                      <Tooltip
                        formatter={(value) => [formatYi(Number(value), 2), "持仓市值"]}
                        contentStyle={TOOLTIP_STYLE}
                      />
                      <Bar dataKey="aum" fill="#2563eb" radius={[0, 8, 8, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
              <section className="card table-wrap" style={{ marginTop: 14 }}>
                <h2>股票明细</h2>
                <p>
                  {filteredStocks.length} / {stocks.count} 只。点击一行查看哪些基金持有。
                </p>
                <div className="toolbar">
                  <input
                    className="search"
                    value={stockQuery}
                    placeholder="搜索股票名称 / 代码"
                    onChange={(event) => setStockQuery(event.target.value)}
                  />
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>股票</th>
                      <th className="num">持有基金</th>
                      <th className="num">持仓市值</th>
                      <th className="num">最高占净值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStocks.map((item) => (
                      <tr key={item.股票代码} onClick={() => setSelectedStock(item)}>
                        <td>{item.序号}</td>
                        <td>
                          <div>{item.股票名称}</div>
                          <div className="type-pill">{item.股票代码}</div>
                        </td>
                        <td className="num">{item.持有基金数}</td>
                        <td className="num">{formatYi(item.持仓市值_亿元, 2)}</td>
                        <td className="num">{formatPct(item.最高占净值)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          ) : !stocksError ? (
            <p className="status">正在读取持股…</p>
          ) : null}
        </>
      ) : null}

      {view === "funds" ? (
        <>
      <section className="kpis">
        <article className="card kpi">
          <span>入池产品</span>
          <strong>{data.count}</strong>
        </article>
        <article className="card kpi">
          <span>合计规模</span>
          <strong>{formatYi(kpis.total, 0)}</strong>
        </article>
        <article className="card kpi">
          <span>平均规模</span>
          <strong>{formatYi(kpis.avg, 1)}</strong>
        </article>
        <article className="card kpi">
          <span>最大产品</span>
          <strong>{kpis.top ? formatYi(kpis.top.规模_亿元, 0) : "—"}</strong>
        </article>
      </section>

      <section className="grid-2">
        <article className="card panel">
          <h2>类型结构</h2>
          <p>只统计偏股口径，不含货币、债券和指数 ETF。</p>
          <div className="chart">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={typeChart} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92} paddingAngle={3}>
                  {typeChart.map((item) => (
                    <Cell key={item.name} fill={TYPE_COLORS[item.name] ?? "#9ca3af"} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value, name, extra) => [
                    `${value} 只 · ${formatYi(Number(extra.payload.aum), 0)}`,
                    String(name),
                  ]}
                  contentStyle={TOOLTIP_STYLE}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="card panel">
          <h2>规模分布</h2>
          <p>按合并后净资产分段，看池子是集中在 50–80 亿还是更大的产品。</p>
          <div className="chart">
            <ResponsiveContainer>
              <BarChart data={buckets}>
                <CartesianGrid stroke="#eef0f3" vertical={false} />
                <XAxis dataKey="name" tick={CHART_TICK} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={CHART_TICK} axisLine={false} tickLine={false} />
                <Tooltip
                  formatter={(value) => [`${value} 只`, "产品数"]}
                  contentStyle={TOOLTIP_STYLE}
                />
                <Bar dataKey="value" fill="#2563eb" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      <section className="card panel">
        <h2>规模排行</h2>
        <p>当前筛选下的前 12 名，点击右侧表格可看单产品详情。</p>
        <div className="chart" style={{ height: 420 }}>
          <ResponsiveContainer>
            <BarChart data={topBars} layout="vertical" margin={{ left: 16, right: 16 }}>
              <CartesianGrid stroke="#eef0f3" horizontal={false} />
              <XAxis type="number" tick={CHART_TICK} axisLine={false} tickLine={false} />
              <YAxis
                type="category"
                dataKey="name"
                width={148}
                tick={CHART_AXIS}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                formatter={(value) => [formatYi(Number(value)), "规模"]}
                labelFormatter={(_, payload) => String(payload?.[0]?.payload.full ?? "")}
                contentStyle={TOOLTIP_STYLE}
              />
              <Bar dataKey="aum" radius={[0, 8, 8, 0]}>
                {topBars.map((item) => (
                  <Cell key={item.full} fill={TYPE_COLORS[item.type] ?? "#2563eb"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="card table-wrap" style={{ marginTop: 14 }}>
        <h2>基金池明细</h2>
        <p>
          {filtered.length} / {funds.length} 只产品。搜索名称或代码，筛选类型后点击一行。
        </p>
        <div className="toolbar">
          <input
            className="search"
            value={query}
            placeholder="搜索产品名称 / 基金代码"
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="chips">
            {types.map((item) => (
              <button
                key={item}
                className={item === type ? "chip active" : "chip"}
                onClick={() => setType(item)}
                type="button"
              >
                {item}
              </button>
            ))}
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>产品</th>
              <th>类型</th>
              <th className="num">规模</th>
              <th className="num">份额</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((item) => (
              <tr key={item.代表代码} onClick={() => setSelected(item)}>
                <td>{item.序号}</td>
                <td>
                  <div>{item.产品名称}</div>
                  <div className="type-pill">
                    {item.代表代码} · {item.代表简称}
                  </div>
                </td>
                <td>
                  <span className="type-pill">
                    <span className="type-dot" style={{ background: TYPE_COLORS[item.基金类型] }} />
                    {item.基金类型}
                  </span>
                </td>
                <td className="num">{formatYi(item.规模_亿元)}</td>
                <td className="num">{item.份额只数}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
        </>
      ) : null}

      {selected ? (
        <div className="overlay" onClick={() => setSelected(null)}>
          <aside className="drawer" onClick={(event) => event.stopPropagation()}>
            <h2>{selected.产品名称}</h2>
            <p className="drawer-meta">
              {selected.基金类型} · 代表份额 {selected.代表代码}
            </p>
            <dl className="kv">
              <dt>合并规模</dt>
              <dd>{formatYi(selected.规模_亿元)}</dd>
              <dt>报告期</dt>
              <dd>{formatQuarter(selected.报告期)}</dd>
              <dt>联接基金</dt>
              <dd>{selected.是否联接 ? "是" : "否"}</dd>
            </dl>
            <div className="shares">
              {selected.份额代码.split(",").map((code) => (
                <span className="share" key={code}>
                  {code}
                </span>
              ))}
            </div>
            {fundHoldings ? (
              <>
                <p className="drawer-meta" style={{ marginTop: 18 }}>
                  {formatQuarter(fundHoldings.report_quarter)} · 持股 {fundHoldings.count} 只
                  <span className={fundHoldings.disclosure === "全部持股" ? "tag full" : "tag top"}>
                    {fundHoldings.disclosure}
                  </span>
                </p>
                {holdingsQuarters.length > 1 ? (
                  <div className="period-tabs compact">
                    {holdingsQuarters.map((label) => (
                      <button
                        key={label}
                        type="button"
                        className={holdingsQuarter === label ? "period-tab active" : "period-tab"}
                        onClick={() => setHoldingsQuarter(label)}
                      >
                        {formatQuarter(label)}
                      </button>
                    ))}
                  </div>
                ) : null}
                <table>
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>股票</th>
                      <th className="num">占净值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fundHoldings.holdings.map((item) => (
                      <tr key={item.股票代码}>
                        <td>{item.序号}</td>
                        <td>
                          {item.股票名称}
                          <div className="type-pill">{item.股票代码}</div>
                        </td>
                        <td className="num">{formatPct(item.占净值比例)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : (
              <p className="note">尚未拉到该基金持仓，请运行 python -m ingest.holdings。</p>
            )}
            <button className="close" type="button" onClick={() => setSelected(null)}>
              关闭
            </button>
          </aside>
        </div>
      ) : null}

      {selectedStock ? (
        <div className="overlay" onClick={() => setSelectedStock(null)}>
          <aside className="drawer" onClick={(event) => event.stopPropagation()}>
            <h2>{selectedStock.股票名称}</h2>
            <p className="drawer-meta">{selectedStock.股票代码}</p>
            <dl className="kv">
              <dt>持有基金</dt>
              <dd>{selectedStock.持有基金数}</dd>
              <dt>持仓市值</dt>
              <dd>{formatYi(selectedStock.持仓市值_亿元, 2)}</dd>
              <dt>最高占净值</dt>
              <dd>{formatPct(selectedStock.最高占净值)}</dd>
            </dl>
            {stockDetail ? (
              <table style={{ marginTop: 16 }}>
                <thead>
                  <tr>
                    <th>基金</th>
                    <th className="num">占净值</th>
                    <th>口径</th>
                  </tr>
                </thead>
                <tbody>
                  {stockDetail.holders.map((item) => (
                    <tr key={`${item.基金代码}-${item.股票代码}`}>
                      <td>
                        {item.产品名称}
                        <div className="type-pill">{item.基金代码}</div>
                      </td>
                      <td className="num">{formatPct(item.占净值比例)}</td>
                      <td>
                        <span className={item.披露口径 === "全部持股" ? "tag full" : "tag top"}>{item.披露口径}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="note">正在读取持有该股的基金…</p>
            )}
            <button className="close" type="button" onClick={() => setSelectedStock(null)}>
              关闭
            </button>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
