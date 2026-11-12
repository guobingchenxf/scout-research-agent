# Scout 运行、使用与部署手册

> 面向第一次拿到仓库的人。按“最快启动 → 干净环境 → 前端开发 → Docker → 可选能力 → 验证 → 排错”组织。
>
> 当前机器（Windows）已经具备 `.venv`、`data/scout.db`、`frontend/dist`，可以直接跳到 0。

## 0. 最快启动（本机已初始化）

```bash
cd D:\scout
.venv\Scripts\python.exe -m scout.cli serve --host 127.0.0.1 --port 8000
```

打开 **http://127.0.0.1:8000/task**。

- 前端已构建在 `frontend/dist`，后端会直接托管。
- 语料已 ingest 到 `data/scout.db`（306 docs / 1244 chunks）。
- 默认 mock planner：离线、确定、不花钱。
- 停止：终端 `Ctrl+C`；如果端口被占用，先结束 8000 端口进程。

## 1. 干净环境从零跑

要求：Python 3.10+、Node 22+（构建前端）、Docker Desktop（可选，仅 Docker 部署需要）。

```bash
cd D:\scout

# 1) Python 虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2) 后端依赖（在 backend 目录下安装 editable 包）
cd backend
pip install -e ".[dev]"

# 3) 初始化数据库 + 导入冻结语料
python -m scout.cli init
python -m scout.cli ingest

# 4) 构建前端
cd ..\frontend
npm install
npm run build

# 5) 启动（后端会托管 frontend/dist）
cd ..\backend
..\.venv\Scripts\python.exe -m scout.cli serve --host 127.0.0.1 --port 8000
```

打开 **http://127.0.0.1:8000/task**。

如果只想跑 CLI，不启动 UI：

```bash
cd D:\scout\backend
..\.venv\Scripts\python.exe -m scout.cli run --question "..." --planner mock
..\.venv\Scripts\python.exe -m scout.cli eval --system scout --planner mock --limit 5
```

## 2. 前端开发模式（热更新）

两个终端：

```bash
# 终端 1：后端
cd D:\scout\backend
..\.venv\Scripts\python.exe -m scout.cli serve --host 127.0.0.1 --port 8000
```

```bash
# 终端 2：前端
cd D:\scout\frontend
npm run dev
```

打开 **http://127.0.0.1:5173**。Vite 把 `/v1` 和 `/health` 代理到 8000。

改完前端要出静态产物时：

```bash
cd D:\scout\frontend
npm run build
```

## 3. Docker 单机部署

需要 Docker Desktop 正在运行。

```bash
cd D:\scout
cp .env.example .env     # 已有 .env 可跳过
docker compose up --build
```

打开 **http://127.0.0.1:8000**。

容器行为：

- Node stage 构建前端，复制 `dist` 到 `/app/static`；
- 安装 Python 包，复制冻结语料与 eval set；
- 启动时 `init → ingest → uvicorn`；
- 挂载 `./data` 作为 SQLite；
- 暴露 `/health` healthcheck。

注意：

- 镜像不打包 `.env`，Compose 在运行时注入。
- **不要在容器运行时用 host CLI 写同一个 `data/scout.db`**：Windows bind mount 上并发 SQLite 写可能损坏 DB。先 `docker compose down`，或给 host 设置独立的 `SCOUT_DB_PATH`。
- 这不是公网部署。公网托管（Render/Fly/VPS/Cloud Run + 域名 + 持久化 + key 管理）不在仓库范围内。

## 4. 使用流程

打开 UI 后：

1. **任务**：输入问题，选 Planner。
   - `mock`：离线、确定、不花钱；答案是抽取式拼接，可能像文档摘录。
   - `deepseek-flash`：真实 LLM，需要 `.env` 里的 `DEEPSEEK_API_KEY`，单题约 30–45 秒。
2. **运行**：时间线、steps/tokens、trace 链接；右上角可直接“查看报告”。
3. **证据板**：子问题覆盖、evidence、冲突、缺口。
4. **报告**：answer、claims、citations、gaps、conflicts；可导出 Markdown。
5. **评测**：读取 `reports/eval_*.json` 的 50 题结果。
6. **审批**：HITL 记录。
7. **来源/策略**：allowlist、capability、sandbox 配置。

所有页面都有独立 URL，可直接打开或分享：

```text
/task
/runs/<run_id>
/runs/<run_id>/evidence
/runs/<run_id>/report
/runs/<run_id>/approvals
/eval
/sources
```

## 5. 配置

复制 `.env.example` 为 `.env`。最常用的变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 空 | live planner 需要；不要提交 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI-compatible |
| `SCOUT_ALLOWED_MODELS` | `deepseek-flash` | 模型 allowlist |
| `SCOUT_LLM_MODE` | `mock` | `mock` 或 `live` |
| `SCOUT_DB_PATH` | `./data/scout.db` | SQLite |
| `SCOUT_CORPUS_DIR` | `./corpus` | 冻结语料 |
| `SCOUT_STATIC_DIR` | `./frontend/dist` | 前端产物 |
| `SCOUT_MAX_STEPS` | `25` | 单 run 步数预算 |
| `SCOUT_TOKEN_BUDGET` | `60000` | 单 run token 预算 |
| `SCOUT_COST_INPUT_PER_1K` | `0` | 计价后才报告 $/task |
| `SCOUT_COST_OUTPUT_PER_1K` | `0` | 同上 |
| `SCOUT_SANDBOX_BACKEND` | `disabled` | `disabled` / `subprocess` / `docker` |

### 可选：真实获取路径

默认只走 API adapter，以下都关着。改 `.env` 后重启 `scout serve`：

```dotenv
# 真实 MCP search（arXiv）
SCOUT_MCP_COMMAND=uvx
SCOUT_MCP_ARGS=["arxiv-mcp-server"]
SCOUT_MCP_TIMEOUT_SECONDS=30

# 固定 RPA workflow
SCOUT_RPA_ENABLED=true

# 只读 GUI fallback
SCOUT_GUI_ENABLED=true
SCOUT_GUI_ALLOWED_HOSTS=docs.vllm.ai,modelcontextprotocol.io
SCOUT_GUI_BROWSER_CHANNEL=msedge
```

- MCP 需要 `uvx` 和网络；arXiv server 首次运行会下载。
- GUI 在 Windows 用本机 Edge；Linux/CI 需要 `playwright install chromium` 并把 channel 留空。
- 验证脚本：`python scripts/verify_live_acquisition.py`。
- 详见 [LIVE_ACQUISITION.md](LIVE_ACQUISITION.md)。

### 可选：Engram 长期记忆

先启动 Engram（它自己的 venv 和 DB）：

```bash
cd D:\engram
uvicorn --factory engram.api:get_app --host 127.0.0.1 --port 8001
```

再给 Scout 加：

```dotenv
SCOUT_ENGRAM_URL=http://127.0.0.1:8001
SCOUT_ENGRAM_USER_ID=scout
SCOUT_ENGRAM_TENANT_ID=
SCOUT_ENGRAM_API_KEY=
```

- 失败 fail-open：Engram 挂了不会让 research run 挂掉。
- 记忆只是规划上下文，不是证据。
- 验证脚本：`python scripts/verify_engram.py --url http://127.0.0.1:8001`。
- 详见 [MEMORY.md](MEMORY.md)。

## 6. 验证

```bash
# 后端测试（116 passed）
cd D:\scout\backend
..\.venv\Scripts\python.exe -m pytest

# lint / type
..\.venv\Scripts\python.exe -m ruff check src tests
..\.venv\Scripts\python.exe -m mypy src/scout

# 前端构建
cd D:\scout\frontend
npm run build

# 前端 e2e（需要后端已启动）
cd D:\scout
.venv\Scripts\python.exe scripts\e2e_frontend.py --base-url http://127.0.0.1:8000

# 真实获取路径（MCP / RPA / GUI）
.venv\Scripts\python.exe scripts\verify_live_acquisition.py

# Engram memory
.venv\Scripts\python.exe scripts\verify_engram.py --url http://127.0.0.1:8001
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

期望：`{"ok":true,"documents":306,"chunks":1244,...}`。

## 7. 排错

| 现象 | 处理 |
|---|---|
| `Address already in use` / 8000 被占 | 结束占用 8000 的进程，或换 `--port 8001` |
| UI 打开是 404 / 空白 | 先 `cd frontend && npm run build`；确认 `SCOUT_STATIC_DIR=./frontend/dist` |
| 选 deepseek 报 key 错误 | `.env` 配 `DEEPSEEK_API_KEY`；改完重启 |
| DB 被锁 / 损坏 | 停掉 Docker 容器和所有 host 进程；必要时恢复备份，避免并发写同一个 SQLite |
| `playwright` 浏览器不存在 | Windows 用 `--gui-channel msedge`；或 `python -m playwright install chromium` |
| MCP 起不来 | 确认 `uvx` 在 PATH、网络可用；`uvx arxiv-mcp-server --help` 自检 |
| Engram 连不上 | 确认 8001 `/health` 正常，`SCOUT_ENGRAM_URL` 正确 |
| 报告页没有答案 | 先在“运行”页确认 status=finished；mock 的答案是抽取式拼接，不是综合回答 |

## 8. 停止与清理

```bash
# 前台服务
Ctrl+C

# Docker
docker compose down

# 查看端口
netstat -ano | findstr :8000
```

运行时产物：`data/`、`reports/`、`frontend/dist/`、`corpus/index/` 都不进 git。

## 9. 相关文档

- [README](../README.md) / [README 中文](../README.zh-CN.md)：项目概览与快速开始
- [DEMO.md](DEMO.md)：3 分钟演示脚本
- [LIVE_ACQUISITION.md](LIVE_ACQUISITION.md)：MCP / RPA / GUI 的真实运行
- [MEMORY.md](MEMORY.md)：Engram memory 适配
- [API.md](API.md)：FastAPI 接口
- [EVALUATION.md](EVALUATION.md)：评测设计、held-out、校准状态
- [SECURITY.md](SECURITY.md)：安全边界
- [frontend/README.md](../frontend/README.md)：前端说明
