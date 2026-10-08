# ingest

拉基金列表、规模、前十大持仓，写入 `data/raw/`。

```bash
python -m ingest.universe
```

当前会拉取：

- `ak.fund_name_em()`：公募名单与基金类型
- 天天基金季报规模明细：期末净资产（亿元）
- 天天基金持股：中报/年报全部持股；若尚未披露则退回季报前十大

- 持股之后可跑 `python -m ingest.returns`：按披露持仓冻结推算每日涨幅，并对照基金实际净值日增长率
- 全市场股票类日终估算规模：`python -m ingest.aum_estimate`（季报净资产 × 净值涨跌，不含申赎；写出 `equity_aum_estimate.json`）

限速和重试在 `eastmoney.py`。前十大持仓仍待下一阶段。
