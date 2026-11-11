# Scout 3 分钟演示脚本

> 目标：证明 Scout 不是“聊天 + RAG demo”，而是一个有证据板、评测、安全和可回放 trace 的研究 Agent。

## 0. 启动（演示前完成）

```bash
cd D:\scout\backend
python -m scout.cli init
python -m scout.cli ingest
python -m scout.cli serve --host 127.0.0.1 --port 8000

# 另开终端
cd D:\scout\frontend
npm run dev
```

打开 `http://127.0.0.1:5173`。

## 1. 任务（0:00–0:40）

在任务页输入：

> vLLM 和 SGLang 在 KV cache 管理上的核心差异是什么？

Planner 选：

- `mock`：离线、确定、不花钱，适合现场演示；
- `deepseek-flash`：真实 LLM planner，需要网络和 key。

点击“开始调研”。

讲解点：

- 场景是 AI 技术调研，不是通用助手；
- 工具只有 5 个：search / read / python / ask_human / finish；
- 获取路径优先 API/MCP，固定流程 RPA，GUI 只读兜底。

## 2. 运行时间线（0:40–1:30）

在“运行”页展示：

1. `plan`：拆子问题、选择 search；
2. `tool_result`：hybrid BM25 + embedding 检索；
3. `read`：读取 vLLM/SGLang 文档；
4. `reflect`：覆盖度、证据数、缺口；
5. `run_finished`：状态、步数、token、成本。

讲解点：

- 每次工具调用都有参数、结果、耗时；
- 事件写入 SQLite + JSONL trace，可回放；
- 预算是硬边界，耗尽时输出“带缺口的报告”。

## 3. 证据板与报告（1:30–2:10）

切到“证据板”：

- 子问题覆盖：q1/q2/q3 的 status 和 evidence_ids；
- 每条证据：claim、quote、doc_id、trust、retrieval_method；
- 冲突和缺口单独列出。

切到“报告”：

- 每个 claim 绑定 citation；
- 没有证据的 claim 不出现；
- 缺口不会用“看起来合理”的话补全；
- 可导出 Markdown。

讲解点：

- citation-first 不是“答案后面加链接”，而是 claim 到 evidence 的结构化绑定；
- 引用校验：quote 必须能在源文档中找到。

## 4. 评测面板（2:10–2:45）

切到“评测”：

- 50 题：fact 10 / multi_hop 15 / comparison 10 / procedure 5 /
  conflict 5 / abstention 5；
- 指标：pass rate、citation support、steps、tokens、p50/p95、失败分类；
- 现有结果：
  - full offline RAG **18/50**，Scout mock **17/50**；
  - full 50 live（DeepSeek flash）：Scout **28/50（56%）**，RAG **18/50（36%）**；
    comparison 7/10 vs 3/10、abstention 4/5 vs 0/5、conflict 2/5 vs 0/5、
    multi-hop 7/15 vs 6/15 更好；fact 7/10 持平；procedure 1/5 vs 2/5 落后。

讲解点（必须诚实）：

- 评测系统工作正常，能暴露差距；
- mock planner 不做综合/弃权，不是质量 baseline；
- full 50 live Scout 28/50，已超过 RAG 18/50；comparison/abstention/conflict/
  multi-hop 更好，procedure 仍弱；
- 失败主要是 missing_fact、procedure 综合、长尾重试；
- 下一步是 procedure 证据聚合、conflict rubric、索引缓存/更快的 fastembed。

## 5. 安全边界（2:45–3:00）

切到“来源/策略”：

- 域名 allowlist、API sources、sandbox backend、capabilities；
- 默认只读；写操作需要 HITL；
- 36 个安全用例：SSRF、注入、密钥脱敏、沙箱边界、审计链、HITL。

一句话收尾：

> Engram 让“写记忆”可信；Scout 让“获取证据和写结论”可信。两者共享
> provenance、trace、eval 和对抗测试的方法论。

## 备用方案

- 没有 DeepSeek：全程用 `mock` planner。
- 没有网络：语料已冻结在 `corpus/`，检索和评测不依赖外网。
- 没有 Docker：本地直接跑后端 + Vite；Docker 只用于最终交付验证。

## 自动生成截图 / 录屏

后端启动后（`http://127.0.0.1:8000`），用 Playwright 驱动本机 Edge，
自动跑一道 mock 任务并抓取任务页、时间线、证据板、报告、评测、来源页：

```bash
python -m playwright install ffmpeg   # 第一次录屏需要
python scripts/capture_demo.py --base-url http://127.0.0.1:8000
```

产物在 `docs/assets/`（截图 + `demo.webm`）。mock planner 不调用外网，
可离线复现。

## P1 新增：深链、e2e、memory

- 每个视图都有独立 URL，可直接打开或分享：
  - `/task`
  - `/runs/<run_id>`
  - `/runs/<run_id>/evidence`
  - `/runs/<run_id>/report`
  - `/runs/<run_id>/approvals`
  - `/eval`
  - `/sources`
- 前端有 error boundary 和 404 页；后端对未知前端路径返回 `index.html`。
- e2e：`python scripts/e2e_frontend.py --base-url http://127.0.0.1:8000`
  （需要后端 + 构建后的前端）。
- Engram memory：设置 `SCOUT_ENGRAM_URL` 后，run 开始会检索长期记忆，
  finished 后写入一条 episodic memory；启动与验证见 `docs/MEMORY.md`。
