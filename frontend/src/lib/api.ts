// API client for the CompliGuard FastAPI backend.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface Scenario {
  id: string;
  customer_id: string;
  reason: string;
  recipient?: string;
  country?: string;
  total_amount?: number;
  num_transactions?: number;
  supporting_document?: string | null;
  _expected?: string;
}

export interface CaseSummary {
  case_id: string;
  customer_id?: string;
  typology?: string;
  alert_type?: string;
  priority?: string;
  status?: string;
  risk_score?: number;
  risk_level?: string;
  recommendation?: string;
  updated_at?: string;
}

export interface EvidenceItem {
  evidence_id: string;
  source_type: string;
  source_id: string;
  field: string;
  value: string | number | boolean;
  description: string;
}

export interface RiskFactor {
  rule_id?: string;
  factor?: string;
  name?: string;
  points?: number;
  severity?: string;
  evidence?: string;
  evidence_ids?: string[];
}

export interface Rationale {
  agent: string;
  rationale?: string;
  confidence?: number;
  evidence?: string[];
  duration_ms?: number;
  model_name?: string | null;
  prompt_version?: string;
  ruleset_version?: string;
  policy_version?: string;
}

export interface TimelineEvent {
  time?: string;
  transaction_id?: string;
  direction?: string;
  amount?: number;
  recipient?: string;
  country?: string;
  transaction_type?: string;
  new_recipient?: boolean;
  purpose?: string | null;
  source_of_funds?: string | null;
  risk_note?: string;
}

export interface GraphFindings {
  fan_out_count?: number;
  fan_in_count?: number;
  hop_count?: number;
  common_recipient?: string[];
  circular_flow?: boolean;
  rapid_forwarding_detected?: boolean;
  possible_layering_path?: string[];
  graph_risk_score?: number;
}

export interface PolicyCitation {
  policy_id?: string;
  chunk_id?: string;
  title?: string;
  section?: string;
  category?: string;
  source?: string;
  retrieval_score?: number;
  rerank_score?: number;
  content?: string;
}

export interface CaseSnapshot {
  case_id: string;
  status?: string;
  triage?: Record<string, unknown>;
  data_quality?: Record<string, unknown>;
  fp_review?: Record<string, unknown>;
  clearance_note?: { status?: string; clearance_reason?: string; evidence?: string[]; recommended_action?: string };
  transaction_findings?: Record<string, unknown>;
  timeline_findings?: { timeline?: TimelineEvent[]; summary?: string };
  graph_findings?: GraphFindings;
  kyc_findings?: Record<string, unknown>;
  watchlist_findings?: Record<string, unknown>;
  adverse_media_findings?: Record<string, unknown>;
  memory_findings?: Record<string, unknown>;
  retrieved_policies?: PolicyCitation[];
  risk_score?: number;
  rule_score?: number;
  ai_score?: number;
  risk_level?: string;
  risk_factors?: RiskFactor[];
  key_drivers?: string[];
  recommendation?: string;
  confidence?: number;
  confidence_factors?: string[];
  priority?: string;
  priority_reason?: string;
  sla_due_at?: string | null;
  sla_label?: string;
  risk_explanation?: string;
  sar_package?: Record<string, unknown>;
  sar_draft?: string;
  review?: Record<string, unknown>;
  human_decision?: string;
  human_review?: Record<string, unknown>;
  errors?: { agent?: string; error?: string }[];
  audit?: string[];
  evidence?: EvidenceItem[];
  audit_rationales?: Rationale[];
  a2a_messages?: { from: string; status?: string; confidence?: number; duration_ms?: number }[];
}

export interface LearnedPattern {
  recipient?: string;
  typology?: string | null;
  source_case_id?: string;
  source_customer_id?: string;
  created_at?: string;
}

export interface LearningSummary {
  patterns_learned: number;
  patterns: LearnedPattern[];
}

export interface AuditEvent {
  id?: number;
  case_id?: string;
  agent_name?: string;
  event_type?: string;
  message?: string;
  confidence?: number;
  created_at?: string;
}

export interface StreamProgress {
  agent: string;
  label: string;
  status: string;
  confidence?: number | null;
  message?: string;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

export const api = {
  scenarios: () => get<Scenario[]>("/scenarios"),
  cases: () => get<CaseSummary[]>("/cases"),
  learning: () => get<LearningSummary>("/learning"),
  case: (id: string) => get<CaseSnapshot>(`/case/${encodeURIComponent(id)}`),
  config: () => get<Record<string, unknown>>("/config"),
  rules: () => get<Record<string, unknown>>("/rules"),
  auditEvents: (limit = 120) => get<{ events: AuditEvent[]; governance: Record<string, string> }>(`/audit-events?limit=${limit}`),
  reloadRules: () => post<Record<string, unknown>>("/rules/reload", {}),
  reindexPolicies: () => post<Record<string, unknown>>("/policies/reindex", {}),
  decide: (id: string, body: Record<string, unknown>) =>
    post<CaseSnapshot>(`/case/${encodeURIComponent(id)}/decision`, body),
  sarExportUrl: (id: string, format: "pdf" | "docx" | "markdown") =>
    `${API_BASE}/case/${encodeURIComponent(id)}/export-sar?format=${format}`,
  sarPreviewUrl: (id: string) =>
    `${API_BASE}/case/${encodeURIComponent(id)}/export-sar?format=pdf&inline=true`,
};

export function toAlert(s: Scenario): Scenario {
  const { _expected, ...alert } = s;
  void _expected;
  return alert;
}

// Upload a document; the backend LLM extracts the alert fields.
export async function extractAlertFromFile(file: File): Promise<Scenario & { _source_filename?: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API_BASE}/alerts/extract`, { method: "POST", body: fd });
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}));
    throw new Error(detail.detail || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

export async function streamInvestigation(
  alert: Scenario,
  handlers: {
    onProgress?: (p: StreamProgress) => void;
    onDone?: (d: { case_id: string; status?: string; risk_score?: number; risk_level?: string }) => void;
    onError?: (e: string) => void;
  }
): Promise<void> {
  const r = await fetch(`${API_BASE}/investigate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(alert),
  });
  if (!r.ok || !r.body) {
    handlers.onError?.(`${r.status} ${r.statusText}`);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const block of events) {
      const evMatch = block.match(/event:\s*(.+)/);
      const dataMatch = block.match(/data:\s*([\s\S]+)/);
      if (!dataMatch) continue;
      const event = evMatch?.[1]?.trim();
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(dataMatch[1].trim());
      } catch {
        continue;
      }
      if (event === "progress") handlers.onProgress?.(data as unknown as StreamProgress);
      else if (event === "done") handlers.onDone?.(data as { case_id: string });
      else if (event === "error") handlers.onError?.(String(data.error ?? "error"));
    }
  }
}
