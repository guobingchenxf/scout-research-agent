import { useEffect, useState } from "react";
import { getEvalSummaries } from "../api";
import type { EvalSummary } from "../types";

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function EvalDashboard() {
  const [summaries, setSummaries] = useState<EvalSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getEvalSummaries()
      .then((items) => setSummaries([...items].reverse()))
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <section className="view">
      <header className="view-head">
        <div>
          <p className="eyebrow">Evaluation</p>
          <h1>评测面板</h1>
          <p className="muted">
            读取 `reports/eval_*.json`：pass rate、citation support、steps、tokens、延迟、失败分类。
          </p>
        </div>
      </header>
      {error ? <p className="error">{error}</p> : null}
      {summaries.length === 0 ? (
        <div className="card">
          <p className="muted">
            还没有评测 summary。先运行：
            <code>python -m scout.cli eval --system scout --planner mock</code>
          </p>
        </div>
      ) : (
        <div className="stack">
          {summaries.map((item) => (
            <div className="card" key={item.file ?? `${item.system}-${item.planner}`}>
              <div className="card-head">
                <h2>
                  {item.system} / {item.planner}
                </h2>
                <span className="muted small">{item.file}</span>
              </div>
              <div className="metric-row">
                <span>tasks <strong>{item.summary.tasks}</strong></span>
                <span>pass <strong>{pct(item.summary.pass_rate)}</strong></span>
                <span>citation <strong>{pct(item.summary.citation_support_rate)}</strong></span>
                <span>steps <strong>{item.summary.avg_steps.toFixed(2)}</strong></span>
                <span>tokens <strong>{Math.round(item.summary.total_tokens ?? 0)}</strong></span>
                <span>p95 <strong>{Math.round(item.summary.p95_latency_ms)} ms</strong></span>
              </div>
              {item.summary.by_category ? (
                <table className="table">
                  <thead>
                    <tr>
                      <th>category</th>
                      <th>tasks</th>
                      <th>pass</th>
                      <th>citation</th>
                      <th>steps</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(item.summary.by_category).map(([category, block]) => (
                      <tr key={category}>
                        <td>{category}</td>
                        <td>{block.tasks}</td>
                        <td>{pct(block.pass_rate)}</td>
                        <td>{pct(block.citation_support_rate)}</td>
                        <td>{block.avg_steps.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
              {item.summary.failure_counts ? (
                <div className="chips">
                  {Object.entries(item.summary.failure_counts).map(([name, count]) => (
                    <span className="chip static" key={name}>
                      {name}: {count}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
