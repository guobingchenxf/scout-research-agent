# Scout 设计文档

> 版本：0.1  
> 状态：Phase 0（设计与骨架），未运行  
> 关联：`SECURITY.md`、`EVALUATION.md`、`PHASES.md`

## 1. 目的

Scout 是一个 **citation-first 的 AI 技术调研 Agent**。它在一个冻结的
AI / Agent / RecSys 语料上回答多跳研究问题，并把每个结论绑定到可核验的证据。

它解决的不是“再做一个 RAG demo”，而是三个工程问题：

1. **证据获取**：优先 API/MCP，固定流程用 RPA，无接口页面用只读 GUI 兜底。
2. **证据质量**：claim 级引用、引用支持校验、冲突暴露、缺口显式化。
3. **证据安全**：不可信内容不能注入指令，代码在沙箱里跑，动作受 capability 约束。

## 2. 垂直场景

**AI 技术调研与选型**，面向 AI 工程师、技术 PM、战略/投资团队。

五类任务：

1. 框架/模型对比（vLLM vs SGLang vs TensorRT-LLM）
2. 文献综述（Agent memory、RAG、LLM4Rec）
3. Benchmark 核验（某模型在某 benchmark 上的表现及来源）
4. 架构/论文拆解（方法、假设、取舍）
5. 生态/趋势扫描（开源项目、论文、采用情况）

## 3. 非目标

- 通用聊天助手
- 多 Agent 编排平台
- 任意网站的通用浏览器 Agent
- 金融/医疗/法律等高风险领域研究
- 微调 / RL
- 生产级分布式基础设施

## 4. 核心原则

1. **证据先于文字**：没有证据的 claim 不出现在最终报告里；无法覆盖的子问题写入 gaps。
2. **获取方式可替换**：Agent 只表达“查/读”，路由层决定 API、MCP、RPA 还是 GUI。
3. **默认只读**：写操作、外部提交、白名单外域名都需要 HITL。
4. **不可信内容不执行**：网页和文档里的“指令”只是数据。
5. **可回放**：每个决策、工具调用、证据、引用都有 trace 和 hash。
6. **离线可测**：mock planner + hash embedding 让 CI 不依赖网络和模型。

## 5. 总体架构

```text
React Frontend
  │ REST + SSE
FastAPI Backend
  │
Agent Runtime
  Intake → Clarify → Plan → Acquire → Extract → Synthesize
         → Verify → (Replan | Finish | Escalate)
  │
Acquisition Router
  1. API adapter
  2. MCP tool
  3. RPA workflow
  4. read-only GUI fallback
  │
Policy Engine + Capability Tokens + Hash-chained Audit
  │
Sandbox (Python, no network) + Frozen Corpus + Source Allowlist
```

## 6. 混合获取层

### 6.1 路由顺序

```text
resolve(source, intent):
  1. 官方 API 可用且允许        → api
  2. MCP tool 可用且允许        → mcp
  3. 匹配固定 RPA workflow      → rpa
  4. 页面只读且域名在白名单     → gui
  5. 否则                       → fail(reason)，必要时 ask_human
```

路由顺序是**策略**，不是硬编码：`SCOUT_ACQUISITION_ORDER` 可配置，但默认
`api,mcp,rpa,gui`。

### 6.2 路径职责

| 路径 | 适用 | 约束 | 输出 |
|---|---|---|---|
| API | arXiv、Semantic Scholar、GitHub、HuggingFace、官方文档 | 白名单、速率、响应大小、缓存 | `SourceDocument` |
| MCP | web search、fetch、filesystem、论文检索 | 工具白名单、schema 校验、超时 | `SourceDocument` |
| RPA | 每日 arXiv 列表、GitHub 指标、leaderboard 快照 | 无 LLM、固定 selector、只读、失败即停 | 快照 + diff |
| GUI | 无 API 的 leaderboard、定价页、博客 | 只读、白名单、不提交表单、不登录、限速 | 文本 + 截图 + a11y 快照 |

### 6.3 来源信任

- `primary`：官方文档、论文原文、代码仓库
- `secondary`：技术博客、第三方整理、GUI 抓取页面
- `untrusted`：用户粘贴内容、未知网页、评论区

规则：

- `untrusted` 不能单独支撑关键 claim。
- GUI 抓取默认 `secondary`，除非域名在 `primary` 白名单。
- 每条证据记录 `retrieval_method` 和 `policy_verdict`。

## 7. Agent Runtime

### 7.1 状态机

```text
INTAKE → CLARIFY? → PLAN → ACQUIRE → EXTRACT → SYNTHESIZE
              ↑                              │
              └──────── REFLECT ◄────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       REPLAN         FINISH        ESCALATE
```

- `CLARIFY` 只在问题缺少关键约束时触发。
- `ACQUIRE` 可并行多个 search/read。
- `EXTRACT` 把文档变成 claim + quote + span。
- `REFLECT` 检查支持度、覆盖度、冲突、时效、预算。
- `FINISH` 只在每个保留 claim 都有 citation 时允许。

### 7.2 ResearchState

```json
{
  "question": "string",
  "constraints": {
    "depth": "shallow | deep",
    "sources": ["arxiv", "github", "docs"],
    "language": "zh",
    "deadline_seconds": 300
  },
  "plan": [
    {"id": "q1", "text": "string", "status": "pending | in_progress | covered | gap"}
  ],
  "coverage": {
    "q1": {"status": "covered", "evidence_ids": ["e1", "e2"]}
  },
  "evidence_board": [
    {
      "id": "e1",
      "claim": "string",
      "source_id": "arxiv:2309.06180",
      "span": "Section 4.2",
      "quote": "string",
      "trust": "primary | secondary | untrusted",
      "support": "direct | indirect | conflicting",
      "retrieval_method": "api | mcp | rpa | gui"
    }
  ],
  "conflicts": [
    {"claim_a": "e1", "claim_b": "e7", "reason": "string"}
  ],
  "gaps": [
    {"subquestion_id": "q3", "reason": "no evidence", "attempts": 2}
  ],
  "budget": {
    "steps": 0,
    "tokens": 0,
    "cost_usd": 0.0,
    "deadline": "2026-11-09T12:00:00Z"
  },
  "history": [],
  "approvals": []
}
```

### 7.3 角色

- **Planner**：拆子问题，选择下一批 search/read，决定是否足够。
- **Executor**：执行工具调用；所有调用经过 Policy。
- **Reflector**：逐 claim 检查证据支持、引用匹配、冲突、覆盖、预算；决定 replan/finish/escalate。

Planner、Synthesis 和 Judge 统一使用 `deepseek-flash`；`SCOUT_ALLOWED_MODELS`
默认只允许 `deepseek-flash`，`deepseek-v4-pro` 被禁用。模型调用都通过同一个
`LLMClient`，可被 `MockLLM` 替换。

### 7.4 工具

| 工具 | 输入 | 输出 | 约束 |
|---|---|---|---|
| `search` | query, sources, k | `SearchHit[]` | 白名单、速率、缓存 |
| `read` | source_id, locator | `SourceDocument` | 只读；走路由 |
| `python` | code, stdin? | stdout/stderr/artifacts | 沙箱、无网络、资源限制 |
| `ask_human` | question, options, risk | decision | 模糊/高风险/超预算 |
| `finish` | report, claims, citations, gaps, confidence | final | 每个 claim 必须有 citation |

### 7.5 记忆

- 会话状态：`ResearchState`，持久化到 SQLite，可 replay。
- 长期记忆：可选 Engram adapter，存用户偏好、项目上下文、上次结论。
- 反事实：改一条 Engram 记忆，观察报告是否变化，用 Engram explain 定位。

## 8. 引用与证据模型

```text
Claim ──1:N── Citation ──1:1── Evidence ──1:1── SourceSpan
```

- `Claim`：报告中的一句可核验陈述。
- `Citation`：claim 到 evidence 的绑定，包含 `quote` 和 `span`。
- `Evidence`：从 `SourceDocument` 抽取的原文片段。
- `SourceSpan`：doc id + section/offset + content hash。

校验规则：

1. `quote` 必须能在 source span 中找到（归一化后模糊匹配）。
2. `source_id` 必须存在且通过白名单。
3. `untrusted` 证据不能作为唯一引用。
4. 冲突证据必须进入 `conflicts`，不能被静默平均。

## 9. 后端 API

```text
POST /v1/runs                       创建调研任务
GET  /v1/runs/{id}                  状态/结果
GET  /v1/runs/{id}/events           SSE
POST /v1/runs/{id}/approvals/{aid}  审批
GET  /v1/runs/{id}/report           Markdown/JSON
GET  /v1/runs/{id}/trace            trace/replay
GET  /v1/eval/summary               评测汇总
GET  /v1/sources                    来源与能力
GET  /v1/policies                   当前策略
GET  /health                        公开
```

## 10. 前端

React + Vite + TypeScript + Tailwind，SSE 接实时事件。

页面：任务、运行时间线、证据板、报告、评测面板、审批、来源/策略。

## 11. 评测摘要

50 题、6 类、gold evidence、规则 + LLM judge + 人工校准、4 个 baseline。
详见 `EVALUATION.md`。

## 12. 安全摘要

capability token、域名白名单、SSRF 防护、Docker 沙箱、注入防御、密钥脱敏、
hash-chained audit、预算/限流。详见 `SECURITY.md`。

## 13. 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 单一 Agent 还是多 Agent | 单 Agent | 可评测、可调试；多 Agent 不是当前 JD 的硬需求 |
| Agent 是否感知 API/GUI/RPA | 否，路由层决定 | 降低 prompt 复杂度，策略集中 |
| 检索 | BM25 + embedding hybrid | 可离线、可解释、可对比 |
| 默认 embedding | hash，可选 fastembed | CI 确定性；真实检索可升级 |
| LLM 默认 | mock | 防止误花钱；live 显式开启 |
| 存储 | SQLite | 单机可复现；后续可换 Postgres |
| 报告格式 | Markdown + JSON | 人可读、机可评 |
| 写操作 | 默认禁止 | 研究 Agent 不需要写外部系统 |

## 14. 开放问题

- 语料许可证逐条核验的工作量（Phase 1 处理）。
- fastembed 在 Windows + Python 3.10 的安装体积和首次下载。
- DeepSeek `deepseek-flash` 的实际上下文长度和限流。
- 是否需要在 Phase 5 加 Redis；当前先用进程内队列。
