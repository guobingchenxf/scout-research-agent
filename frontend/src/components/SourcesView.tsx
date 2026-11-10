import { useEffect, useState } from "react";
import { getPolicies, getSources } from "../api";
import type { PoliciesInfo, SourcesInfo } from "../types";

export default function SourcesView() {
  const [sources, setSources] = useState<SourcesInfo | null>(null);
  const [policies, setPolicies] = useState<PoliciesInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getSources(), getPolicies()])
      .then(([sourceInfo, policyInfo]) => {
        setSources(sourceInfo);
        setPolicies(policyInfo);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <section className="view">
      <header className="view-head">
        <div>
          <p className="eyebrow">Security boundary</p>
          <h1>来源与策略</h1>
          <p className="muted">
            API → MCP → RPA → GUI 的路由边界、域名白名单、capability 和沙箱状态。
          </p>
        </div>
      </header>
      {error ? <p className="error">{error}</p> : null}
      <div className="grid-2">
        <div className="card">
          <h2>允许的来源</h2>
          {sources ? (
            <>
              <p className="muted small">
                sandbox: {sources.sandbox_backend} · verify_dns:{" "}
                {String(sources.verify_dns)}
              </p>
              <div className="chips">
                {sources.api_sources.map((source) => (
                  <span className="chip static" key={source}>
                    {source}
                  </span>
                ))}
              </div>
              <h3>域名白名单</h3>
              <div className="chips">
                {sources.allowlist.map((host) => (
                  <span className="chip static" key={host}>
                    {host}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <p className="muted">加载中…</p>
          )}
        </div>
        <div className="card">
          <h2>Capabilities</h2>
          {policies ? (
            <>
              <div className="chips">
                {policies.capabilities.map((capability) => (
                  <span className="chip static" key={capability}>
                    {capability}
                  </span>
                ))}
              </div>
              <h3>运行配置</h3>
              <table className="table">
                <tbody>
                  {[
                    "llm_mode",
                    "embedding_provider",
                    "model_planner",
                    "model_judge",
                    "enable_synthesis",
                    "require_auth",
                  ].map((key) => (
                    <tr key={key}>
                      <td>{key}</td>
                      <td>{String(policies.config[key] ?? "")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <p className="muted">加载中…</p>
          )}
        </div>
      </div>
    </section>
  );
}
