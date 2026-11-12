import { Link } from "react-router-dom";
import type { EventRecord, RunRecord } from "../types";
import EvidenceBoard from "./EvidenceBoard";
import Timeline from "./Timeline";

interface Props {
  run: RunRecord | null;
  events: EventRecord[];
  onRefresh: () => void;
}

export default function RunView({ run, events, onRefresh }: Props) {
  if (!run) {
    return (
      <div className="card">
        <h2>Run</h2>
        <p className="muted">正在读取运行状态…</p>
      </div>
    );
  }

  return (
    <section className="view">
      <header className="view-head">
        <div>
          <p className="eyebrow">Run {run.id.slice(0, 8)}</p>
          <h1>{run.question}</h1>
          <p className="muted small">
            created {run.created_at}
            {run.ended_at ? ` · ended ${run.ended_at}` : " · in progress"}
          </p>
        </div>
        <div className="row">
          <Link className="button primary" to={`/runs/${run.id}/report`}>
            查看报告
          </Link>
          <a
            className="button"
            href={`/v1/runs/${run.id}/trace/view`}
            target="_blank"
            rel="noreferrer"
          >
            查看 trace
          </a>
          <button className="button" onClick={onRefresh}>
            刷新
          </button>
        </div>
      </header>

      <div className="grid-run">
        <Timeline run={run} events={events} />
        <div className="card">
          <h2>本次运行</h2>
          <div className="metric-row vertical">
            <span>status <strong>{run.status}</strong></span>
            <span>steps <strong>{run.result?.state?.budget.steps ?? 0}</strong></span>
            <span>evidence <strong>{run.result?.state?.evidence_board.length ?? 0}</strong></span>
            <span>gaps <strong>{run.result?.report?.gaps.length ?? 0}</strong></span>
          </div>
          {run.result?.report ? (
            <>
              <p className="answer-preview">{run.result.report.answer}</p>
              <p className="muted small">
                每个 claim 的 citation 在报告页：{" "}
                <Link to={`/runs/${run.id}/report`}>查看完整报告 →</Link>
              </p>
            </>
          ) : (
            <p className="muted small">报告尚未生成。</p>
          )}
        </div>
      </div>

      <EvidenceBoard state={run.result?.state} />
    </section>
  );
}
