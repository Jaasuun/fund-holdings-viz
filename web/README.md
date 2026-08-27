# web

可视化前端（Vite / React）。页面有：科技偏离、日涨幅、持股排行、基金池。

```bash
# 终端 1
uvicorn api.main:app --reload --port 8000

# 终端 2
cd web && npm install && npm run dev
```

打开 http://127.0.0.1:5173 。前端通过 Vite 代理读取 `/api`。
