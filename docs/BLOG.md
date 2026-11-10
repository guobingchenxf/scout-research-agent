# Scout：一个 citation-first 的研究 Agent，以及它还没解决的三个问题

## 为什么要做 Scout

大多数“Deep Research Agent” demo 长这样：一个问题 → 检索几段网页 → 让模型写一段带链接的回答。它能演示，但很难回答三个工程问题：

1. 每个结论真的被证据支持吗？
2. 来源冲突时，Agent 是暴露分歧，还是编一个“平均答案”？
3. 工具失败、页面没有 API、内容里有注入时，Agent 还能安全地继续吗？

Scout 是一个面向 AI 技术调研的窄场景 Agent，设计目标不是“什么都能聊”，而是把证据获取、证据质量和证据安全做成闭环。它和 Engram 组成一对：Engram 管“写记忆”的可信，Scout 管“获取证据和写结论”的可信。

## 架构

```text
React UI (SSE)
   │
FastAPI
   │
Agent runtime: plan → acquire → extract → synthesize → verify → replan
   │
Acquisition router: API → MCP → RPA → read-only GUI
   │
Policy + capability + audit + HITL
   │
Frozen corpus + SQLite + Docker/subprocess sandbox
```

几个关键决定：

- **单 Agent，不是多 Agent。** 当前 JD 需要的是可评测、可调试的 harness，不是更多角色。
- **Agent 不感知获取方式。** 它只说“查/读”，路由层决定 API、MCP、RPA 还是 GUI。
- **证据板是核心状态。** 每条证据带 doc_id、quote、trust、support、retrieval_method；报告只保留有 citation 的 claim。
- **默认只读。** 写操作、白名单外域名、高风险动作都需要 HITL。
- **评测先行。** 50 题任务集、规则 grader、LLM judge、baseline、失败分类是产品的一部分。

## 证据与引用

Scout 的 claim 不是自然语言句子加一个链接，而是：

```text
Claim → Citation → Evidence → SourceSpan
```

引用校验会检查 quote 是否能在源文档中找到；untrusted 来源不能单独支撑关键结论；冲突证据进入 `conflicts`，不会被静默平均。报告会显式列出 gaps：哪些子问题没覆盖、为什么、还缺什么。

这带来一个反直觉的结果：**报告可能比 RAG 更短、更不“完整”，但每个结论更能被追问。** 这正是研究 Agent 应该有的取舍。

## 评测结果（诚实版）

50 题任务集覆盖 fact / multi_hop / comparison / procedure / conflict / abstention。

Full 50 offline：

| 系统 | 总体 | fact | multi_hop | comparison | procedure | conflict | abstention |
|---|---:|---:|---:|---:|---:|---:|---:|
| single-shot RAG（offline） | 18/50 | 7/10 | 6/15 | 3/10 | 2/5 | 0/5 | 0/5 |
| Scout mock（offline） | 17/50 | 5/10 | 4/15 | 4/10 | 0/5 | 0/5 | 4/5 |
| Scout live（flash） | **28/50** | 7/10 | **7/15** | **7/10** | 1/5 | **2/5** | **4/5** |

Full 50 live（DeepSeek flash，max_steps=10）：citation 94%，avg 8.66 步，
27.3k tokens/task，p50 39.9s，p95 77.4s。

**结论：Scout full 50 live 28/50 已超过 RAG 18/50**；comparison、
abstention、conflict、multi-hop 更好，fact 持平，procedure 仍弱。失败模式：

1. **procedure 综合弱**：流程题需要按步骤重组证据，当前倾向拼接摘要；
2. **冲突覆盖有限**：conflict 2/5，仍依赖 prompt + 简单启发式；
3. **missing_fact 17**：多跳/比较题仍会漏掉 gold 中的关键事实；
4. **长尾延迟**：comparison 有一个重试长尾（category p95 ~659s）；
5. **mock planner 不会综合/弃权**：它只是运行时 testbed，不是质量 baseline。

两轮质量调优后：grader 中英文分别算覆盖率、稀有词加权 evidence span、
全文读取、reflector 冲突写回、planner finish/多跳/弃权/冲突规则、
conflict/analysis synthesis、abstention gate、title boost + query rewrite。
fact live 从 5/10 提升到 7/10，full 50 live 从 15/50 到 28/50。

## 还没解决的三个问题

### 1. 检索质量

当前默认 hash embedding 只适合 CI 的确定性测试，不适合真实语义检索。下一步：

- 标题/实体 boost；
- fastembed（bge-small-zh）或真正的 embedding API；
- query rewrite / translation；
- rerank 与 MMR 的证据多样性约束。

### 2. 证据到答案的融合

Agent 能找到证据，但“读完 → 写出直接答案”这一步不稳定。下一步：

- 在 finish 前做 evidence-conditioned synthesis；
- 用 claim-level rubric 约束“每个 claim 必须绑定 quote”；
- 对冲突/缺口单独建模，而不是塞进同一段生成。

### 3. Planner 的停止策略

Planner 倾向继续搜索，而不是在证据足够时收敛。下一步：

- 用评测集训练/调 prompt 的 finish policy；
- 把 coverage、evidence count、预算作为显式 stopping features；
- 对 fact/multi-hop 使用不同策略，而不是一个 prompt 打天下。

## 安全

Scout 把安全做成边界，而不是事后补丁：

- capability token：read / write / sandbox / memory / export；
- 域名白名单 + DNS 私网拦截 + 元数据 IP 拦截；
- 中英文注入检测 + untrusted 内容标记 + 密钥脱敏；
- Python 沙箱：Docker 强隔离（no network / read-only / cap-drop / non-root），
  subprocess 仅开发模式；
- GUI 只读：不点击、不登录、不下载；
- SQLite 哈希链审计 + HITL 风险分级。

安全用例 36 个，覆盖 SSRF、注入、沙箱边界、审计链、HITL。

## 学到的东西

1. **评测比功能更值钱。** 一个能诚实暴露 15/50 vs 18/50、再通过调优做到 28/50 vs 18/50 的 harness，比一个“看起来很强”的 demo 更适合面试。
2. **窄场景是优势。** AI 技术调研的边界让证据、来源、冲突和缺口都有意义。
3. **安全是产品的一部分。** 只读、allowlist、沙箱、审计不是“以后再加”，而是 Agent 能否上生产的前提。
4. **不要编数字。** 当前 Agent 没超过 RAG，就写没超过；下一步要做什么，比假装已经做好更重要。

## 下一步

- 用 fastembed / title boost 提升检索；
- 做 evidence-conditioned synthesis，并用 50 题验证；
- 继续攻 conflict / multi-hop / procedure，而不是只刷 fact；
- 加人工校准（judge-human agreement），把评测从“可跑”变成“可信”。
