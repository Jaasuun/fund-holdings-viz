# fund-holdings-viz

统计**规模大于 50 亿元**的公募基金前十大持仓，并做本地可视化。

持仓来自基金季报，不是日频数据。页面会标明报告期。

## 目录

| 路径 | 职责 |
| --- | --- |
| `ingest/` | 拉基金列表、规模、前十大持仓，写入 `data/raw/` |
| `transform/` | 清洗、去重、交叉统计，写入 `data/processed/` |
| `api/` | 只读缓存，给前端 JSON |
| `web/` | 可视化前端（Vite / React，阶段 5） |
| `data/` | 本地缓存，不入库 |

## 状态

阶段 0 已完成：目录骨架、依赖声明和忽略规则已就绪。拉数口径（产品范围、多份额去重、排序指标）确认后再做阶段 1。

## 本地环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```
