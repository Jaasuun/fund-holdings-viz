# fund-holdings-viz

统计**规模大于 50 亿元**的公募基金前十大持仓，并做本地可视化。

持仓来自基金季报，不是日频数据。页面会标明报告期。

## 目录

| 路径 | 职责 |
| --- | --- |
| `ingest/` | 拉基金列表、规模、前十大持仓，写入 `data/raw/` |
| `transform/` | 清洗、去重、交叉统计，写入 `data/processed/` |
| `api/` | 只读缓存，给前端 JSON |
| `web/` | 可视化前端（Vite / React） |
| `data/` | 本地缓存，不入库 |

## 口径

- 产品范围：偏股公募（`股票型`、`混合型-偏股`、`QDII-普通股票`、`QDII-混合偏股`）
- 规模：季报期末净资产，单位亿元；**同一主基金的 A/C 等份额持仓相同，规模合并后再筛**
- 入池阈值：合并后规模 **大于 50 亿元**
- 代表份额：优先 A 类，供后续拉持仓使用

## 状态

阶段 1：已接入名单、规模、持股，以及报告期末之后的日涨幅（实际净值 vs 披露持仓推算）。

## 本地环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

生成规模超过 50 亿元的偏股产品池，并拉取持股：

```bash
python -m ingest.universe
python -m ingest.holdings
python -m ingest.returns
```

查看基金池：

```bash
uvicorn api.main:app --reload --port 8000
cd web && npm install && npm run dev
# 浏览器打开 http://127.0.0.1:5173
```
