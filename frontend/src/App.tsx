import { useEffect, useState } from "react";
import { createRun, getHealth, getRun, openEventStream } from "./api";
import type { EventRecord, Planner, RunRecord } from "./types";
import ApprovalsView from "./components/ApprovalsView";
import EvalDashboard from "./components/EvalDashboard";
import EvidenceBoard from "./components/EvidenceBoard";
import ReportView from "./components/ReportView";
import RunView from "./components/RunView";
import SourcesView from "./components/SourcesView";
import TaskForm from "./components/TaskForm";

type View = "task" | "run" | "evidence" | "report" | "eval" | "approvals" | "sources";

const TERMINAL = new Set(["finished", "failed", "escalated"]);

const NAV: Array<{ key: View; label: string; requiresRun?: boolean }> = [
  { key: "task", label: "任务" },
  { key: "run", label: "运行", requiresRun: true },
  { key: "evidence", label: "证据板", requiresRun: true },
  { key: "report", label: "报告", requiresRun: true },
  { key: "eval", label: "评测" },
  { key: "approvals", label: "审批", requiresRun: true },
  { key: "sources", label: "来源/策略" },
];

export default function App() {
  const [view, setView] = useState<View>("task");
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (!runId) return;
    setEvents([]);
    let stopped = false;
    const stop = openEventStream(
      runId,
      (type, payload) => {
        setEvents((previous) =>
          previous.some((item) => item.seq === payload.seq && item.type === payload.type)
            ? previous
            : [...previous, payload],
        );
        if (type === "run_finished" || type === "run_failed") {
          getRun(runId).then(setRun).catch(() => undefined);
        }
      },
      () => {
        if (!stopped) {
          getRun(runId).then(setRun).catch(() => undefined);
        }
      },
    );
    return () => {
      stopped = true;
      stop();
    };
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    if (run && TERMINAL.has(run.status)) return;
    const timer = window.setInterval(() => {
      getRun(runId)
        .then(setRun)
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [runId, run?.status, run]);

  async function start(question: string, planner: Planner) {
    setBusy(true);
    setError(null);
    setEvents([]);
    setRun(null);
    try {
      const result = await createRun({ question, planner, async_mode: true });
      if (!result.run_id) {
        throw new Error("后端没有返回 run_id");
      }
      setRunId(result.run_id);
      setView("run");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function refresh() {
    if (!runId) return;
    getRun(runId)
      .then(setRun)
      .catch((reason: Error) => setError(reason.message));
  }

  const docs = Number(health?.documents ?? 0);
  const chunks = Number(health?.chunks ?? 0);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">S</div>
          <div>
            <h1>Scout</h1>
            <p className="muted small">citation-first research agent</p>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <button
              key={item.key}
              className={view === item.key ? "active" : ""}
              disabled={Boolean(item.requiresRun && !runId)}
              onClick={() => setView(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="health">
          <span className={health ? "pulse" : "pulse off"} />
          <span>{health ? `${docs} docs · ${chunks} chunks` : "offline"}</span>
        </div>
      </header>

      <main className="main">
        {view === "task" ? (
          <TaskForm onStart={start} busy={busy} error={error} />
        ) : null}
        {view === "run" ? (
          <RunView run={run} events={events} onRefresh={refresh} />
        ) : null}
        {view === "evidence" ? (
          <section className="view">
            <header className="view-head">
              <div>
                <p className="eyebrow">Evidence</p>
                <h1>证据板</h1>
                <p className="muted">claim ↔ quote ↔ doc_id；冲突和缺口显式列出。</p>
              </div>
            </header>
            <EvidenceBoard state={run?.result?.state} />
          </section>
        ) : null}
        {view === "report" ? (
          <section className="view">
            <header className="view-head">
              <div>
                <p className="eyebrow">Report</p>
                <h1>报告</h1>
                <p className="muted">每个 claim 绑定 citation；缺口显式保留。</p>
              </div>
            </header>
            <ReportView report={run?.result?.report} />
          </section>
        ) : null}
        {view === "eval" ? <EvalDashboard /> : null}
        {view === "approvals" ? <ApprovalsView runId={runId ?? undefined} /> : null}
        {view === "sources" ? <SourcesView /> : null}
      </main>
    </div>
  );
}
