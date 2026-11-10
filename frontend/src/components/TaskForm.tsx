import { useState } from "react";
import type { Planner } from "../types";

const EXAMPLES = [
  "vLLM 的 PagedAttention 解决什么问题？",
  "vLLM 和 SGLang 在 KV cache 管理上的差异是什么？",
  "对比 Traditional RAG 和 Agentic RAG。",
  "KeepKV 和 Tamarin 对 KV cache merging 的判断一致吗？",
  "vLLM 的企业版授权价格是多少？",
];

interface Props {
  onStart: (question: string, planner: Planner) => Promise<void>;
  busy: boolean;
  error: string | null;
}

export default function TaskForm({ onStart, busy, error }: Props) {
  const [question, setQuestion] = useState("");
  const [planner, setPlanner] = useState<Planner>("mock");

  async function submit() {
    const trimmed = question.trim();
    if (trimmed.length < 2 || busy) return;
    await onStart(trimmed, planner);
  }

  return (
    <section className="view narrow">
      <header className="view-head">
        <div>
          <p className="eyebrow">Citation-first research</p>
          <h1>把一个技术问题交给 Scout</h1>
          <p className="muted">
            优先 API/MCP，固定流程走 RPA，无接口页面用只读 GUI 兜底；每条结论必须绑定证据。
          </p>
        </div>
      </header>

      <div className="card">
        <label className="field">
          <span>研究问题</span>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="例如：vLLM 和 SGLang 在 KV cache 管理上的核心差异是什么？"
            rows={5}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                void submit();
              }
            }}
          />
        </label>

        <div className="form-row">
          <label className="field compact">
            <span>Planner</span>
            <select
              value={planner}
              onChange={(event) => setPlanner(event.target.value as Planner)}
            >
              <option value="mock">mock（离线、不花钱）</option>
              <option value="deepseek">deepseek-flash（真实 LLM）</option>
            </select>
          </label>
          <button
            className="button primary"
            disabled={busy || question.trim().length < 2}
            onClick={() => void submit()}
          >
            {busy ? "创建中…" : "开始调研"}
          </button>
        </div>
        {error ? <p className="error">{error}</p> : null}
      </div>

      <div className="examples">
        <p className="eyebrow">示例问题</p>
        <div className="chips">
          {EXAMPLES.map((example) => (
            <button
              className="chip"
              key={example}
              onClick={() => setQuestion(example)}
              type="button"
            >
              {example}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
