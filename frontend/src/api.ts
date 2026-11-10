import type {
  Approval,
  EventRecord,
  EvalSummary,
  PoliciesInfo,
  Report,
  RunRecord,
  RunRequest,
  SourcesInfo,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  return (await response.json()) as T;
}

export interface CreateRunResponse {
  run_id?: string;
  status?: string;
  report?: Report;
}

export function createRun(payload: RunRequest): Promise<CreateRunResponse> {
  return request<CreateRunResponse>("/v1/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getRun(runId: string): Promise<RunRecord> {
  return request<RunRecord>(`/v1/runs/${runId}`);
}

export function getEvents(runId: string): Promise<EventRecord[]> {
  return request<EventRecord[]>(`/v1/runs/${runId}/events`);
}

export function getApprovals(runId: string): Promise<Approval[]> {
  return request<Approval[]>(`/v1/runs/${runId}/approvals`);
}

export function decideApproval(
  runId: string,
  approvalId: string,
  decision: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/v1/runs/${runId}/approvals/${approvalId}`, {
    method: "POST",
    body: JSON.stringify({ decision, decided_by: "ui" }),
  });
}

export function getEvalSummaries(): Promise<EvalSummary[]> {
  return request<EvalSummary[]>("/v1/eval/summaries");
}

export function getSources(): Promise<SourcesInfo> {
  return request<SourcesInfo>("/v1/sources");
}

export function getPolicies(): Promise<PoliciesInfo> {
  return request<PoliciesInfo>("/v1/policies");
}

export function getHealth(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/health");
}

export function openEventStream(
  runId: string,
  onEvent: (type: string, payload: EventRecord) => void,
  onClose: () => void,
): () => void {
  const source = new EventSource(`/v1/runs/${runId}/events/stream`);
  const types = [
    "run_started",
    "plan",
    "tool_result",
    "reflect",
    "budget_exhausted",
    "run_failed",
    "run_finished",
  ];
  let closed = false;
  for (const type of types) {
    const listener = (event: Event) => {
      const message = event as MessageEvent<string>;
      try {
        onEvent(type, JSON.parse(message.data) as EventRecord);
      } catch {
        // Ignore malformed frames; the next SSE frame may still be valid.
      }
    };
    source.addEventListener(type, listener);
  }
  source.onerror = () => {
    if (closed) return;
    closed = true;
    source.close();
    onClose();
  };
  return () => {
    closed = true;
    source.close();
  };
}
