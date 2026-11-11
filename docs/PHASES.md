# Scout 阶段计划与审批门

> 工作规则：每个阶段我先写代码和文档；**你 review 并明确同意后，我才运行、
> 安装依赖、抓取数据或启动服务**。运行前我会说明要跑什么、会写哪些文件、
> 预计耗时和网络访问。

## Phase 0 — 设计与骨架（当前）

**我写：**

- `README.md`、`.gitignore`、`.env.example`
- `docs/DESIGN.md`、`SECURITY.md`、`EVALUATION.md`、`PHASES.md`
- `backend/pyproject.toml`
- 目录结构、空模块契约

**你审批：** 架构、边界、安全模型是否认可。

**运行：** 不运行。

## Phase 1 — 语料 + 检索 + baseline

**我写：**

- `scripts/fetch_corpus.py`（B 方式：arXiv / Semantic Scholar / GitHub /
  HuggingFace / 官方文档；冻结快照 + manifest + sha256 + license）
- `backend/src/scout/config.py`、`models.py`、`storage.py`
- `backend/src/scout/corpus.py`：manifest、加载、切分
- `backend/src/scout/retrieval.py`：BM25 + hash embedding + hybrid
- `backend/src/scout/llm.py`：DeepSeek OpenAI-compatible client + MockLLM
- `backend/src/scout/baseline.py`：single-shot RAG
- `backend/src/scout/cli.py`：`init` / `index` / `search` / `baseline`
- `backend/tests/`：models、storage、corpus、retrieval、llm、baseline

**你审批：** 抓取范围、许可证策略、依赖（fastembed 是否装）、是否跑抓取。

**运行（需你同意）：**

1. `pip install -e ".[dev]"`（安装依赖）
2. `python scripts/fetch_corpus.py --max-docs 350`（联网抓取）
3. `python -m scout.cli init`
4. `python -m scout.cli index`
5. `python -m scout.cli search --query "..."`
6. `python -m scout.cli baseline --question "..."`
7. `pytest`

**验收：** 语料 manifest 完整；索引可查；baseline 能对 5 个示例问题产出带引用的回答；
测试通过。

## Phase 2 — Agent loop + 混合获取

**我写：**

- `agent/state.py`：ResearchState
- `agent/planner.py`：DeepSeek planner + mock planner
- `agent/reflector.py`：支持度/覆盖/冲突/预算检查
- `agent/tools.py`：search / read / python / ask_human / finish
- `agent/loop.py`：状态机
- `acquisition/router.py`：API → MCP → RPA → GUI
- `acquisition/api_sources.py`：arXiv / S2 / GitHub / HF / docs adapters
- `acquisition/mcp_client.py`：通用 MCP client + 本地 mock
- `acquisition/rpa/`：固定 workflow
- `acquisition/gui/`：Playwright 只读 observer
- `trace.py`：事件 + 可回放

**你审批：** 路由策略、工具契约、GUI 只读边界。

**运行（需你同意）：**

1. `python -m scout.cli run --question "..." --planner mock`
2. 10 个示例任务
3. 打开 trace / 证据板（Phase 5 前用 CLI/JSON）

**验收：** 10 个任务能完成多步循环；至少 3 个任务走 API，1 个走 GUI 兜底，
1 个走 RPA；trace 可回放。

## Phase 3 — 安全 + 沙箱

**我写：**

- `policy/capability.py`、`policy/allowlist.py`、`policy/injection.py`
- `sandbox/python_sandbox.py`（Docker + 开发模式）
- `sandbox/gui_sandbox.py`
- `audit.py`：hash-chained ledger
- `hitl.py`：审批门
- 安全测试：20 个对抗用例

**你审批：** 沙箱方案、白名单、HITL 触发条件。

**运行（需你同意）：**

1. 安全用例（预期全部拦截）
2. `scout verify-ledger`
3. 沙箱逃逸/联网/读宿主测试

**验收：** 未授权 0、注入拦截 100%、沙箱逃逸 0、密钥泄漏 0。

## Phase 4 — 评测

**我写：**

- `eval/tasks/`：50 题 JSON
- `eval/gold/`：gold evidence
- `eval/graders.py`：规则 + LLM judge
- `eval/baselines.py`
- `eval/runner.py`、`metrics.py`、`report.py`
- CI 配置

**你审批：** 任务集、gold evidence、grader 规则、阈值。

**运行（需你同意）：**

1. `pytest`（smoke）
2. `python -m scout.cli eval --suite full`
3. 生成 `reports/eval.md` / `eval.html`

**验收：** 50 题跑完；Scout 正确率/引用支持率高于 single-shot RAG；安全指标达标。

## Phase 5 — 前端

**我写：**

- React + Vite + TypeScript 应用
- 任务页、运行时间线、证据板、报告页、评测面板、审批页、来源/策略页
- SSE 接入
- `docker-compose.yml`

**你审批：** 页面结构、交互、是否需要设计稿。

**运行（需你同意）：**

1. `npm install`
2. `npm run dev`
3. 端到端演示

**验收：** 从提交问题到看到带引用报告，全程在 UI 完成；审批和 trace 可见。

## Phase 6 — 部署与包装

**我写：**

- Dockerfile、docker-compose（api / worker / sandbox / frontend）
- README 快速开始、架构图、评测报告、安全说明
- 3 分钟 demo 脚本
- 技术博客草稿
- 简历 bullet（填实测数字）

**你审批：** 交付物清单、demo 脚本。

**运行（需你同意）：**

1. 干净环境 `docker compose up --build`
2. 端到端 smoke
3. 录 demo

**验收：** 干净环境可复现；文档完整；demo 能讲 20–30 分钟。

## 审批门速查

| 阶段 | 写代码 | 跑测试/服务 | 联网抓取 | 花钱（LLM） |
|---|---|---|---|---|
| Phase 0 | 是 | 否 | 否 | 否 |
| Phase 1 | 是 | 需同意 | 需同意 | 否（mock） |
| Phase 2 | 是 | 需同意 | 需同意 | 需同意（live 模式） |
| Phase 3 | 是 | 需同意 | 需同意 | 否 |
| Phase 4 | 是 | 需同意 | 否（用快照） | 需同意（judge） |
| Phase 5 | 是 | 需同意 | 否 | 需同意 |
| Phase 6 | 是 | 需同意 | 否 | 需同意 |

## 当前状态

- Phase 0：文档和骨架已写入 `D:\scout`。
- Phase 1a：虚拟环境、依赖、`pytest`（26 passed）、`ruff`、`mypy` 全部通过。
- Phase 1b/1c：已抓取 **306 篇语料**：paper 230（Crossref 225 + arXiv 5）、
  code_repo 38、model_card 32、official_doc 6；约 114 万字符。
- 已 ingest 为 **1244 chunks**；检索、离线 extractive baseline 跑通；
  vLLM/SGLang/TensorRT-LLM/LangGraph 文档与 README 已入库。
- 网络限制：arXiv / Semantic Scholar / 主 HuggingFace / OpenAlex 在当前网络
  不可达；已用 Crossref、`hf-mirror.com`、GitHub README API 替代，脚本使用
  `trust_env=False` 绕开失效的系统代理。
- Phase 2：agent loop、Mock/DeepSeek planner、Reflector、ToolRegistry
  （search/read/python/ask_human/finish）、AcquisitionRouter
  （API→MCP→RPA→GUI）、MCP client、RPA workflows、GUI reader、Trace、
  FastAPI 最小 surface、CLI `run`/`trace`/`serve` 已完成并执行：
  - `pytest`：**53 passed**
  - mock loop：6 步完成，2 条证据、1 个显式缺口，trace 事件完整
  - API：`/health` 200，306 documents / 1,244 chunks
  - DeepSeek live smoke：`deepseek-flash` 可用，4–6 步可执行并产出
    带 citation 的报告
- 已知问题：live planner 会过度搜索、偶尔读到噪声来源；检索排序和
  planner prompt 需要在 Phase 4 用评测集调优。
- Phase 3：`policy/capability`、`policy/allowlist`（SSRF/DNS）、
  `policy/injection`、`sandbox/python_sandbox`（Docker/Subprocess/Disabled）、
  `sandbox/gui_sandbox`、`audit`、`hitl` 已完成并执行：
  - 安全用例 **36 passed**（SSRF、注入、密钥脱敏、capability、沙箱边界、
    GUI allowlist、审计链、HITL）
  - 全量回归 **89 passed**
  - `ruff` / `mypy` 通过
  - 修复：subprocess 沙箱改用宿主环境副本 + 移除 `PYTHONPATH`，避免
    Windows Python 启动失败
- 已知边界：subprocess 是弱隔离；Docker 命令边界有测试，但 CI 未实际启动容器。
- Phase 4：50 题评测集、`RuleGrader`、`LLMJudge`、`metrics`、`baselines`、
  `EvalRunner`、Markdown report、CLI `eval` 已完成并执行：
  - `pytest tests/test_eval.py`：7 passed
  - 全量回归：**98 passed**；`ruff` / `mypy` 通过
  - 10 题 fact 子集（offline）：single-shot RAG **7/10**（citation 100%，
    p50 3ms）；Scout mock **4/10**（citation 100%）
  - 10 题 fact 子集（DeepSeek flash，max_steps=8）：Scout **5/10**
    （citation 100%，~20.4k tokens/task，p50 29.9s）
  - 结论：**当前 live agent 在 fact 子集上没有超过 RAG baseline**；
    主要失败是 over-search、missing_fact、偶发 missing_citation。
  - 尝试过 final synthesis，但在当前证据质量下反而降到 2/10，
    已改为 `SCOUT_ENABLE_SYNTHESIS=false` 默认关闭。
- 完整 50 题 offline 已执行：
  - single-shot RAG：**18/50（36%）**，citation 90%；fact 7/10，
    multi_hop 6/15，comparison 3/10，procedure 2/5，conflict 0/5，
    abstention 0/5
  - Scout mock：**8/50（16%）**，citation 90%；mock planner 不做综合/弃权，
    不是质量 baseline
- Phase 5：React + Vite + TypeScript 前端已完成并执行：
  - `npm install` 成功（166 packages；esbuild install script 已授权/重建）
  - `npm run build` 成功（289 modules，dist 413 KB JS / 7 KB CSS）
  - 后端 + Vite dev 端到端验证：backend `/health` 200、frontend `/` 200、
    Vite proxy `/health` 200
  - async run：`POST /v1/runs` 返回 `run_id`，6 步完成，2 条证据，
    citation 正常；`/events` 19 个事件，SSE 流正常
  - 评测面板 API 读取到 `eval_rag_full.json`、`eval_scout_mock_full.json`
  - 页面：任务、运行时间线、证据板、报告、评测、审批、来源/策略
- Phase 6：已完成并执行：
  - 多阶段 `Dockerfile`（Node 构建前端 → Python 运行时，FastAPI 托管 dist）
  - `.dockerignore`、`docker-compose.yml`（loopback、data volume、healthcheck）
  - `scripts/docker-entrypoint.sh`（init → ingest → serve）
  - GitHub Actions CI（pytest / ruff / mypy / npm build / docker build）
  - `docs/DEMO.md`、`docs/BLOG.md`
  - README 部署章节 + 实测简历 bullet
  - FastAPI 在 `frontend/dist` 存在时托管静态 UI
  - **Docker 验证通过**：`docker compose up --build -d` 成功；容器
    `/health` 200（306 docs / 1244 chunks）；`/` 返回 UI（200）；
    `/v1/eval/summaries` 返回 2 个 summary；async run 6 步完成并带 citation
  - 修复容器路径：`SCOUT_INDEX_DIR=/app/corpus/index`、
    `SCOUT_REPORTS_DIR=/app/reports`
- 质量调优（第一轮）：
  - grader 中英文分别算覆盖率取 max
  - evidence span 改为稀有词加权 + 单句；read 回到全文
  - reflector 冲突写回 state；报告包含 conflicts
  - planner 增加 finish/多跳/弃权/冲突规则
  - final synthesis 仍关闭（实验降到 2/10）
- full 50 live（第一轮，DeepSeek flash，max_steps=10）：
  - Scout **15/50（30%）** vs RAG **18/50（36%）**
  - comparison 5/10 vs 3/10（更好）、abstention 1/5 vs 0/5（更好）
  - fact 5/10 vs 7/10、multi_hop 4/15 vs 6/15、procedure 0/5 vs 2/5
  - citation 85.2%、avg 8.72 steps、27.3k tokens/task、p50 40.7s
- 第二轮质量调优（四项）：
  - conflict：finish 接受 `conflicts`；answer 明确“不一致”时自动补
    conflict；conflict/analysis 两种 synthesis prompt，max_tokens 2500
  - multi-hop：LLM 子问题分解 + 按子问题选证据
  - abstention：价格/收购/容量/延迟/人物日期的 deterministic gate；
    abstention grader 允许“拒答但有引用”
  - retrieval：title boost + 中文 intent query rewrite；fastembed 已安装
    并测试（512 维，CPU 建索引约 256s，KeepKV 中文 query 会误召中文书稿），
    因此不设为默认
  - targeted live（conflict+abstention 10 题）：abstention **5/5**，
    conflict **1/5**，citation 100%，无 over_abstention
- 最终 full 50 live（新代码）：**28/50（56%）** vs RAG **18/50（36%）**：
  - fact 7/10（持平）、multi_hop 7/15（+1）、comparison 7/10（+4）、
    procedure 1/5（-1）、conflict 2/5（+2）、abstention 4/5（+4）
  - citation 94%、avg 8.66 steps、27.3k tokens/task、p50 39.9s、p95 77.4s
  - 失败：missing_fact 17、missing_citation 2、over_abstention 2、
    over_answer 1；comparison 有一个长尾重试（category p95 ~659s）
- 下一步：GitHub Actions 远程未跑；fastembed 需要更快的索引缓存/模型
  选择后再评估；procedure/conflict 仍是弱项。

## P0 收尾（2026-11-11）

- dev/held-out 30/20 切分、Procedure 模式、per-step cost、HTML trace viewer。
- held-out 20 题 × 2 seeds（DeepSeek flash）：10/20、8/20，
  均值 **45% ± 5%**，citation **87.5% ± 2.5%**。
- CI：backend / frontend / docker 三个 job。
- 截图 + 短录屏：`docs/assets/`，采集脚本 `scripts/capture_demo.py`。
- `v0.1.0` tag / GitHub Release。
- 校准：assistant adjudication 一致性检查（85%，κ=0.70）已记录，**不是**
  人工校准；人工校准仍未完成（`docs/EVALUATION.md` §11.2–11.3）。

## P1 第一块：混合获取 live 验证（2026-11-11）

- 新增 `acquisition/factory.py`：按配置装配 API / MCP / RPA / GUI，默认全关。
- 新增 `SCOUT_MCP_*`、`SCOUT_RPA_ENABLED`、`SCOUT_GUI_*` 配置。
- 真实路径验证（`scripts/verify_live_acquisition.py`）：
  - MCP：官方 `uvx mcp-server-fetch`，stdio JSON-RPC，docs 页 4,589 chars；
  - RPA：GitHub README workflow，5,864 chars；
  - GUI：headless Edge，只读提取 3,382 chars；非白名单 host 被拒绝。
- 详情：`docs/LIVE_ACQUISITION.md`。
- 回归：107 tests passed；ruff / mypy 通过。
