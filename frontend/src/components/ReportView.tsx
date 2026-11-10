import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Report } from "../types";

interface Props {
  report?: Report;
}

function download(report: Report) {
  const content = report.markdown || report.answer || "";
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "scout-report.md";
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function ReportView({ report }: Props) {
  if (!report) {
    return (
      <div className="card">
        <h2>报告</h2>
        <p className="muted">运行完成后这里会显示 citation-bound 报告。</p>
      </div>
    );
  }

  const markdown =
    report.markdown ||
    `# Scout 报告\n\n${report.answer}\n\n${report.claims
      .map((claim) => `- ${claim.text} [${claim.citations[0]?.doc_id ?? ""}]`)
      .join("\n")}`;

  return (
    <div className="stack">
      <div className="card">
        <div className="card-head">
          <h2>报告</h2>
          <div className="row">
            <span className="badge">confidence {report.confidence.toFixed(2)}</span>
            <button className="button" onClick={() => download(report)}>
              导出 Markdown
            </button>
          </div>
        </div>
        <div className="markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h2>引用</h2>
          {report.citations.length === 0 ? (
            <p className="muted">没有引用。</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>doc_id</th>
                  <th>span</th>
                </tr>
              </thead>
              <tbody>
                {report.citations.map((citation, index) => (
                  <tr key={`${citation.doc_id}-${index}`}>
                    <td><code>{citation.doc_id}</code></td>
                    <td>{citation.span || "document"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="card">
          <h2>缺口与冲突</h2>
          {report.gaps.length === 0 && report.conflicts.length === 0 ? (
            <p className="muted">没有显式缺口或冲突。</p>
          ) : null}
          {report.gaps.map((gap) => (
            <div className="gap" key={gap.subquestion_id}>
              <code>{gap.subquestion_id}</code>
              <p className="muted">{gap.reason}</p>
            </div>
          ))}
          {report.conflicts.map((conflict, index) => (
            <div className="conflict" key={`${conflict.claim_a}-${index}`}>
              <strong>{conflict.claim_a} ↔ {conflict.claim_b}</strong>
              <p className="muted">{conflict.reason}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
