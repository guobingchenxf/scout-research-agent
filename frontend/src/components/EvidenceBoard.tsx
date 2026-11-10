import type { ResearchState } from "../types";

interface Props {
  state?: ResearchState;
}

export default function EvidenceBoard({ state }: Props) {
  if (!state) {
    return (
      <div className="card">
        <h2>证据板</h2>
        <p className="muted">运行开始后，这里会显示子问题覆盖、证据、冲突和缺口。</p>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="card-head">
          <h2>子问题覆盖</h2>
          <span className="muted">{state.plan.length} 个子问题</span>
        </div>
        <div className="plan-list">
          {state.plan.map((item) => {
            const coverage = state.coverage[item.id];
            return (
              <div className="plan-row" key={item.id}>
                <span className={`dot ${coverage?.status ?? "pending"}`} />
                <div>
                  <p>{item.text}</p>
                  <span className="muted small">
                    {coverage?.status ?? "pending"} · {coverage?.evidence_ids.length ?? 0} evidence
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>证据</h2>
          <span className="muted">{state.evidence_board.length} 条</span>
        </div>
        {state.evidence_board.length === 0 ? (
          <p className="muted">还没有证据。</p>
        ) : (
          <div className="evidence-list">
            {state.evidence_board.map((evidence) => (
              <article className="evidence" key={evidence.id}>
                <div className="evidence-head">
                  <span className={`badge trust-${evidence.trust}`}>{evidence.trust}</span>
                  <code>{evidence.doc_id}</code>
                  <span className="muted small">{evidence.retrieval_method}</span>
                </div>
                <p className="evidence-claim">{evidence.claim}</p>
                <blockquote>{evidence.quote}</blockquote>
                <span className="muted small">support: {evidence.support}</span>
              </article>
            ))}
          </div>
        )}
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>冲突</h2>
          {state.conflicts.length === 0 ? (
            <p className="muted">没有检测到冲突。</p>
          ) : (
            state.conflicts.map((conflict, index) => (
              <div className="conflict" key={`${conflict.claim_a}-${index}`}>
                <strong>
                  {conflict.claim_a} ↔ {conflict.claim_b}
                </strong>
                <p className="muted">{conflict.reason}</p>
              </div>
            ))
          )}
        </div>
        <div className="card">
          <h2>缺口</h2>
          {state.gaps.length === 0 ? (
            <p className="muted">没有显式缺口。</p>
          ) : (
            state.gaps.map((gap) => (
              <div className="gap" key={gap.subquestion_id}>
                <code>{gap.subquestion_id}</code>
                <p className="muted">{gap.reason}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
