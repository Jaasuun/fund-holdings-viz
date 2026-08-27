# api

只读 `data/processed/`，给前端 JSON：基金池、重仓股排行、单股下钻、单基金持仓、报告期。

```bash
uvicorn api.main:app --reload
```

当前接口：`GET /api/funds`、`GET /health`。拉数是批任务，本层不打外部接口。前端开发时由 Vite 把 `/api` 代理到本服务。
