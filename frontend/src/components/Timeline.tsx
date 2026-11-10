import type { EventRecord, RunRecord } from "../types";

interface Props {
  run: RunRecord | null;
  events: EventRecord[];
}

function eventTitle(type: string): string {
  switch (type) {
    case "run_started":
      return "Run started";
    case "plan":
      return "Plan";
    case "tool_result":
      return "Tool result";
    case "reflect":
      return "Reflect";
    case "budget_exhausted":
      return "Budget exhausted";
    case "run_failed":
      return "Run failed";
    case "run_finished":
      return "Run finished";
    default:
      return type;
  }
}

function summarize(event: EventRecord): string {
  const payload = event.payload;
  if (event.type === "plan") {
    const tool = String(payload.tool ?? "");
    const rationale = String(payload.rationale ?? "");
    return `${tool}${rationale ? ` · ${rationale}` : ""}`;
  }
  if (event.type === "tool_result") {
    const ok = payload.ok === true ? "ok" : "error";
    const error = payload.error ? ` · ${String(payload.error)}` : "";
    return `${ok}${error}`;
  }
  if (event.type === "reflect") {
    const notes = Array.isArray(payload.notes) ? payload.notes.join(" · ") : "";
    return notes || "reflection recorded";
  }
  if (event.type === "run_finished") {
    return `status=${String(payload.status ?? "")} steps=${String(payload.steps ?? "")}`;
  }
  return Object.keys(payload).slice(0, 4).join(", ");
}

export default function Timeline({ run, events }: Props) {
  const state = run?.result?.state;
  const budget = state?.budget;
  return (
    <div className="card">
      <div className="card-head">
        <h2>运行时间线</h2>
        {run ? <span className={`badge status-${run.status}`}>{run.status}</span> : null}
      </div>
      {budget ? (
        <div className="metric-row">
          <span>steps <strong>{budget.steps}</strong></span>
          <span>tokens <strong>{budget.tokens}</strong></span>
          <span>cost <strong>${budget.cost_usd.toFixed(4)}</strong></span>
        </div>
      ) : null}
      {events.length === 0 ? (
        <p className="muted">等待事件流…</p>
      ) : (
        <ol className="timeline">
          {events.map((event) => (
            <li className={`event event-${event.type}`} key={`${event.seq}-${event.type}`}>
              <div className="event-head">
                <span className="event-seq">#{event.seq}</span>
                <strong>{eventTitle(event.type)}</strong>
                <span className="event-time">{event.ts.slice(11, 19)}</span>
              </div>
              <p className="event-summary">{summarize(event)}</p>
            </li>
          ))}
        </ol>
      )}
      {run?.result?.error ? <p className="error">{run.result.error}</p> : null}
    </div>
  );
}
