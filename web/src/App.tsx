import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchFunds } from "./api";
import { formatQuarter, formatYi } from "./format";
import { TYPE_COLORS, type Fund, type FundsResponse } from "./types";

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

export default function App() {
  const [data, setData] = useState<FundsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("全部");
  const [selected, setSelected] = useState<Fund | null>(null);

  useEffect(() => {
    fetchFunds()
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, []);

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
            A/C 等份额已按主基金合并。规模为季报期末净资产，持仓尚未接入，当前先看基金池结构。
          </p>
        </div>
        <div className="badge">{formatQuarter(data.report_quarter)}</div>
      </header>

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
            <p className="note">同一主基金的 A/C 份额持仓相同，已合并规模。前十大持仓下一阶段接入。</p>
            <button className="close" type="button" onClick={() => setSelected(null)}>
              关闭
            </button>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
