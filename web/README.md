# web

可视化前端（Vite / React）。第一版展示规模超过 50 亿元的偏股基金池：概览指标、类型结构、规模分布、排行和明细。

```bash
# 终端 1
uvicorn api.main:app --reload --port 8000

# 终端 2
cd web && npm install && npm run dev
```

打开 http://127.0.0.1:5173 。前端通过 Vite 代理读取 `/api/funds`。
