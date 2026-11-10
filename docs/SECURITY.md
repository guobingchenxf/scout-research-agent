# Scout 安全设计

> 目标：Scout 可以访问不可信网页、执行代码、调用外部工具，但**不能越权、
> 不能泄密、不能被抓取的页面劫持**。

## 1. 威胁模型

| 威胁 | 攻击面 | 对策 |
|---|---|---|
| Prompt injection | 网页、PDF、GitHub README、用户粘贴内容 | 内容标记 untrusted；不执行内容中的指令；工具调用只由 Planner 产生；注入模式检测 |
| SSRF | `read(url)`、MCP fetch | 域名白名单；DNS/IP 检查；禁止私网/环回/云元数据；重定向复查 |
| 沙箱逃逸 | `python(code)` | Docker；非 root；`--network none`；只读挂载；tmpfs；CPU/内存/时间限制 |
| 密钥泄漏 | 日志、trace、报告、prompt | 只在环境变量；日志脱敏；trace 存 fingerprint；不把 key 放进 prompt |
| 未授权写操作 | RPA/GUI/API | 默认 read-only；capability token；写操作必须 HITL |
| 数据外泄 | 报告导出、外部请求 | egress 白名单；禁止任意 POST；导出 DLP |
| 供应链 | 依赖、沙箱 pip | 锁版本；沙箱内禁止 pip install；只读镜像 |
| 审计篡改 | 本地 DB | hash-chained audit；`scout verify-ledger` |
| 成本失控 | LLM/抓取 | 每 run 预算；速率限制；熔断；最大步数 |
| 证据投毒 | 不可信来源写成 primary | 信任级别由来源决定，不由内容声明；untrusted 不能单独支撑 claim |

## 2. Capability 模型

每个 run 获得一组 capability，默认最小：

```text
sources:read          读白名单来源
sources:write         默认不授予（外部提交/表单）
sandbox:exec          沙箱执行 Python
memory:read           读 Engram 记忆
memory:write          写 Engram 记忆（可关闭）
report:export         导出报告（可能触发 HITL）
```

Policy Engine 对每次工具调用返回：

```json
{"decision": "allow | deny | require_approval", "reason": "..."}
```

决策写入 audit ledger。

## 3. 来源白名单与 SSRF

- `SCOUT_SOURCE_ALLOWLIST` 是域名列表（支持后缀匹配）。
- 默认允许：`arxiv.org`、`api.semanticscholar.org`、`api.github.com`、
  `huggingface.co`、`docs.vllm.ai`、`docs.sglang.ai`、`nvidia.github.io`、
  `langchain-ai.github.io`、`modelcontextprotocol.io`。
- 解析 URL 后：
  1. 只允许 `https`（本地测试允许 `http://127.0.0.1` 的 mock portal）。
  2. 解析 DNS，拒绝私有网段、环回、链路本地、云元数据地址。
  3. 跟随重定向时重新校验。
  4. 限制响应大小（默认 5 MB）和内容类型。
- MCP fetch 走同一套校验，不允许 MCP server 绕过。

## 4. 沙箱

### 4.1 Python 沙箱

- 优先 Docker：`--network none`、`--read-only`、`--tmpfs /tmp`、
  `--memory 512m`、`--cpus 1`、`--pids-limit 128`、非 root。
- 挂载：`corpus/` 只读；`/work` 可写；无宿主 home。
- 捕获 stdout/stderr，限制输出大小。
- 超时默认 10s。
- 开发模式（无 Docker）：受限子进程，明确标注“弱隔离”，不允许在生产使用。

### 4.2 GUI 沙箱

- 独立 Playwright context；禁用下载、上传、剪贴板、权限弹窗。
- 只读导航：不点击提交按钮、不填表单、不登录。
- 域名白名单；页面脚本可禁用或严格限制。
- 截图和 DOM 快照存本地，默认不进报告。

### 4.3 RPA 沙箱

- 固定 workflow（YAML/JSON），无 LLM。
- selector 和输出 schema 固定；页面结构变化即失败，不猜。
- 只读；失败即停并记录。

## 5. 不可信内容处理

1. 所有抓取内容带 `trust` 和 `retrieval_method`。
2. 内容进入 Planner 前，标记为 `[UNTRUSTED CONTENT]`，并去除明显指令模式。
3. 不把网页内容直接拼进 system prompt。
4. 工具调用只能由 Planner 的 JSON 输出产生；内容中的“调用工具”文本不执行。
5. 注入检测：`ignore previous instructions`、`reveal system prompt`、
   `rm -rf`、`exfiltrate` 等模式；命中则降级为证据，不作为指令。
6. 引用校验：quote 必须能在源 span 中找到。

## 6. 密钥与隐私

- `.env` 在 `.gitignore`；不提交。
- 日志/trace/报告中不出现 `DEEPSEEK_API_KEY`、`S2_API_KEY`、`GITHUB_TOKEN`。
- 错误信息脱敏。
- 私有文档默认本地-only；不发送到外部 LLM，除非用户显式允许。

## 7. 审计

```text
audit(id, run_id, seq, actor, action, decision, prev_hash, entry_hash)
```

- 每个工具调用、权限决策、审批、来源抓取都写一条。
- `entry_hash = sha256(prev_hash + canonical_json(record))`。
- `scout verify-ledger` 验证链完整性。
- 审计是 tamper-evident，不是 tamper-proof；生产需外部锚定。

## 8. HITL

触发条件：

1. 问题缺少关键约束（订单/时间/来源）。
2. 访问白名单外域名。
3. 写操作或外部提交。
4. 预算将超（token/成本/时间）。
5. 报告包含敏感内容或准备导出。

审批记录：谁、何时、批准/拒绝、理由。

## 9. 限流与预算

- 每 run：最大步数、token、成本、墙钟时间。
- 每来源：QPS、并发、重试上限。
- 全局：最大并发 run、每 API key 限流。
- 熔断：连续失败/429 时暂停该来源。

## 10. 数据与许可证

- 只抓公开内容；遵守 robots.txt 和 API 条款。
- manifest 记录 `license`、`url`、`fetched_at`、`sha256`。
- 许可证不明确的内容只存链接和摘要，不存全文。
- 冻结快照仅用于本地评测；不重新分发全文。

## 11. 开发模式 vs 生产模式

| 能力 | 开发（Windows 本地） | 生产（Docker） |
|---|---|---|
| Python 沙箱 | 受限子进程（弱隔离） | Docker 强隔离 |
| GUI | 本地 Playwright | 独立浏览器容器 |
| 网络 | 白名单 + 本地 mock | 白名单 + egress proxy |
| 认证 | 可关闭（loopback） | 必须 API key |
| 审计 | 本地 SQLite | SQLite/Postgres + 外部锚定 |

开发模式必须在 README 和启动日志里明确标注，不能当成生产安全。

## 12. 实现状态（Phase 3）

已实现：

- `policy/capability.py`：capability token、工具策略、写操作 approval 路径。
- `policy/allowlist.py`：域名白名单、scheme/credentials/port 检查、
  私网/环回/链路本地/云元数据 IP 拦截、可选 DNS 解析与失败关闭。
- `policy/injection.py`：中英文注入模式检测、untrusted 内容标记、密钥脱敏。
- `sandbox/python_sandbox.py`：`disabled`、弱隔离 `subprocess`、强隔离
  `docker`（`--network none`、`--read-only`、`--cap-drop ALL`、非 root、
  资源限制）。
- `sandbox/gui_sandbox.py`：GUI 只读边界 + allowlist + 注入标记。
- `audit.py`：基于 SQLite 哈希链的审计记录，动作/决策脱敏。
- `hitl.py`：风险分级、审批记录、auto/human 两种决策来源。

默认值：

- `SCOUT_SANDBOX_BACKEND=disabled`；要执行 `python` 必须显式设为
  `subprocess`（弱）或 `docker`（强）。
- `SCOUT_VERIFY_DNS=true`；合成测试域名需要注入 resolver 或关闭 DNS 校验。
- `SCOUT_ALLOW_HTTP_LOCAL=false`；GUI/HTTP 默认只允许 HTTPS。

测试结果（Phase 3）：

- 安全用例 **36 passed**（SSRF、注入、密钥脱敏、capability、沙箱边界、
  GUI allowlist、审计链、HITL）。
- 全量回归 **89 passed**；`ruff` / `mypy` 通过。
- Docker 沙箱目前验证的是命令边界（`--network none`、`--read-only`、
  `--cap-drop ALL`、非 root、资源限制），CI 尚未实际启动容器。

未完成：

- Ed25519/外部锚定审计、egress proxy、seccomp/Job Object 级沙箱加固。
- 生产环境的 DNS/egress 代理和真实 MCP server 验证。
