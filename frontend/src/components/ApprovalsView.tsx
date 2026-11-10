import { useEffect, useState } from "react";
import { decideApproval, getApprovals } from "../api";
import type { Approval } from "../types";

interface Props {
  runId?: string;
}

export default function ApprovalsView({ runId }: Props) {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    if (!runId) return;
    try {
      setApprovals(await getApprovals(runId));
      setError(null);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  useEffect(() => {
    void refresh();
  }, [runId]);

  async function decide(id: string, decision: string) {
    if (!runId) return;
    try {
      await decideApproval(runId, id, decision);
      await refresh();
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  if (!runId) {
    return (
      <div className="card">
        <h2>审批</h2>
        <p className="muted">先创建一次 run，才能查看 HITL 审批记录。</p>
      </div>
    );
  }

  return (
    <section className="view">
      <header className="view-head">
        <div>
          <p className="eyebrow">Human in the loop</p>
          <h1>审批与风险</h1>
          <p className="muted">高风险动作、模糊请求和预算确认会记录在这里。</p>
        </div>
      </header>
      {error ? <p className="error">{error}</p> : null}
      {approvals.length === 0 ? (
        <div className="card">
          <p className="muted">这次运行没有触发人工审批。</p>
        </div>
      ) : (
        <div className="stack">
          {approvals.map((approval) => (
            <div className="card" key={approval.id}>
              <div className="card-head">
                <h2>{approval.question}</h2>
                <span className={`badge risk-${approval.risk}`}>{approval.risk}</span>
              </div>
              <p className="muted small">
                {approval.created_at} · {approval.decided_by ?? "pending"}
              </p>
              {approval.decision ? (
                <p>
                  决定：<strong>{approval.decision}</strong>
                </p>
              ) : (
                <div className="chips">
                  {approval.options.map((option) => (
                    <button
                      className="button"
                      key={option}
                      onClick={() => void decide(approval.id, option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
