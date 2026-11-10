export type Planner = "mock" | "deepseek";

export interface RunRequest {
  question: string;
  constraints?: Record<string, unknown>;
  planner?: Planner;
  async_mode?: boolean;
}

export interface Citation {
  evidence_id?: string;
  doc_id: string;
  span?: string;
  quote?: string;
  url?: string;
}

export interface Claim {
  id: string;
  text: string;
  citations: Citation[];
  support?: string;
}

export interface Evidence {
  id: string;
  claim: string;
  doc_id: string;
  span: string;
  quote: string;
  trust: string;
  support: string;
  retrieval_method: string;
  content_hash?: string;
}

export interface Gap {
  subquestion_id: string;
  reason: string;
  attempts?: number;
}

export interface Conflict {
  claim_a: string;
  claim_b: string;
  reason: string;
}

export interface Report {
  answer: string;
  claims: Claim[];
  citations: Citation[];
  conflicts: Conflict[];
  gaps: Gap[];
  confidence: number;
  markdown: string;
}

export interface PlanItem {
  id: string;
  text: string;
  status: string;
}

export interface Coverage {
  status: string;
  evidence_ids: string[];
}

export interface Budget {
  steps: number;
  tokens: number;
  cost_usd: number;
  deadline?: string | null;
}

export interface HistoryItem {
  step: number;
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  error?: string | null;
}

export interface ResearchState {
  question: string;
  constraints: Record<string, unknown>;
  plan: PlanItem[];
  coverage: Record<string, Coverage>;
  evidence_board: Evidence[];
  conflicts: Conflict[];
  gaps: Gap[];
  budget: Budget;
  history: HistoryItem[];
  approvals: Record<string, unknown>[];
}

export interface RunRecord {
  id: string;
  question: string;
  constraints: Record<string, unknown>;
  status: string;
  created_at: string;
  ended_at?: string | null;
  result?: {
    report?: Report;
    state?: ResearchState;
    error?: string | null;
  } | null;
  error?: string | null;
}

export interface EventRecord {
  seq: number;
  type: string;
  payload: Record<string, unknown>;
  ts: string;
}

export interface Approval {
  id: string;
  run_id: string;
  question: string;
  risk: string;
  options: string[];
  decision?: string | null;
  decided_by?: string | null;
  note?: string;
  created_at: string;
  decided_at?: string | null;
}

export interface CategoryBlock {
  tasks: number;
  passed: number;
  pass_rate: number;
  citation_support_rate: number;
  avg_steps: number;
  avg_tokens?: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  total_cost_usd: number;
}

export interface EvalSummary {
  file?: string;
  system: string;
  planner: string;
  summary: {
    tasks: number;
    passed: number;
    pass_rate: number;
    citation_support_rate: number;
    avg_steps: number;
    avg_tokens?: number;
    total_tokens?: number;
    p50_latency_ms: number;
    p95_latency_ms: number;
    total_cost_usd: number;
    failure_counts?: Record<string, number>;
    by_category?: Record<string, CategoryBlock>;
  };
}

export interface SourcesInfo {
  allowlist: string[];
  api_sources: string[];
  sandbox_backend: string;
  verify_dns: boolean;
}

export interface PoliciesInfo {
  config: Record<string, unknown>;
  capabilities: string[];
}
