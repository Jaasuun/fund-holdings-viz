# ingest

拉基金列表、规模、前十大持仓，写入 `data/raw/`。

```bash
python -m ingest.universe
```

当前会拉取：

- `ak.fund_name_em()`：公募名单与基金类型
- 天天基金季报规模明细：期末净资产（亿元）

限速和重试在 `eastmoney.py`。前十大持仓仍待下一阶段。
