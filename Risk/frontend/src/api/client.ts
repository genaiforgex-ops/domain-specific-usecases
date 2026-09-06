const API_BASE = import.meta.env.VITE_API_URL || "";

// The session lives in the `genaiforge_session` httpOnly cookie, set server-side by
// /auth/login. It is deliberately invisible to JavaScript.
// `credentials: "include"` is what makes the browser store and resend it.
export const FETCH_CREDENTIALS: RequestCredentials = "include";

/**
 * A failed HTTP response, carrying its status.
 *
 * Callers need to tell "this doesn't exist" (404) apart from "the request
 * failed" (401/500/offline). Without the status they look identical, and code
 * that treats every error as "not found" takes the create-it path on a
 * transient blip — which is how opening a vendor could kick off a fresh,
 * billable due-diligence run.
 */
export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

/** A message worth showing, whatever the server sent back.
 *
 * res.statusText used to be the fallback, but HTTP/2 removed reason phrases — so
 * behind the nginx ingress it is ALWAYS "". Any error whose body was not the
 * expected JSON (a 500 from Starlette, an ingress 502/504) therefore produced an
 * ApiError with an empty message and a toast with no text at all. Locally it
 * looked fine, because Vite serves HTTP/1.1 where statusText is populated.
 *
 * FastAPI's `detail` is a string for HTTPException but an array of objects for a
 * 422 validation error, and an array is truthy — so it has to be narrowed rather
 * than trusted.
 */
function errorMessage(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  // 422: [{ loc: [...], msg: "field required" }, ...]
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : ""))
      .filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  return STATUS_FALLBACK[status] ?? `Request failed (HTTP ${status})`;
}

const STATUS_FALLBACK: Record<number, string> = {
  400: "That request wasn't valid.",
  401: "Your session has expired. Please sign in again.",
  403: "You don't have permission to do that.",
  404: "Not found.",
  413: "That file is too large to upload.",
  422: "Some of the values sent weren't valid.",
  500: "Something went wrong on the server.",
  502: "The server is unreachable. Please try again.",
  503: "The service is temporarily unavailable.",
  504: "The server took too long to respond.",
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: FETCH_CREDENTIALS,
  });
  if (!res.ok) {
    if (res.status === 401) {
      window.dispatchEvent(new Event("genaiforge:unauthorized"));
    }
    const err = await res.json().catch(() => ({ detail: "" }));
    throw new ApiError(errorMessage(err.detail, res.status), res.status);
  }
  if (res.headers.get("content-type")?.includes("application/pdf")) {
    return res.blob() as unknown as T;
  }
  // A 204 has no body, so res.json() throws "Unexpected end of JSON input" and
  // every DELETE reported a failure the server had actually carried out. Checked
  // by status rather than by parsing, because 204 is defined to have no content.
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as unknown as T;
  }
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(`/api/v1${path}`),
  post: <T>(path: string, body?: unknown) =>
    request<T>(`/api/v1${path}`, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(`/api/v1${path}`, { method: "PATCH", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(`/api/v1${path}`, { method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(`/api/v1${path}`, { method: "DELETE" }),
  upload: <T>(path: string, formData: FormData) =>
    request<T>(`/api/v1${path}`, { method: "POST", body: formData, headers: {} }),
};

export interface User {
  id: string;
  email: string;
  display_name: string;
  roles: string[];
  is_active?: boolean;
  last_login?: string | null;
  created_at?: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

/** Runtime auth config from GET /auth/config. */
export interface AuthConfig {
  environment: string;
  sso_enabled: boolean;
}

export interface EvidenceItem {
  clause_id?: string;   // UUID — exact row used by enrichment
  clause_ref?: string;
  doc_span?: { start: number; end: number };
  // attached server-side from the matched RegulatorClause row
  instrument?: string | null;
  source_doc?: string | null;
  page_no?: number | null;
  para_no?: string | null;
  clause_text?: string | null;
}

interface RegulatorEvidence {
  evidence?: EvidenceItem[];
  clause_ids?: string[];
  reasoning?: string;
  truncated?: boolean;
}

export interface ClassificationJob {
  id: string;
  vendor_id: string;
  document_id?: string | null;
  document_filename?: string | null;
  status: string;
  ai_label: string | null;
  ai_confidence: number | null;
  ai_evidence: RegulatorEvidence | null;
  rbi_label: string | null;
  rbi_confidence: number | null;
  rbi_evidence: RegulatorEvidence | null;
  sebi_label: string | null;
  sebi_confidence: number | null;
  sebi_evidence: RegulatorEvidence | null;
  final_label: string | null;
  justification: string | null;
  requires_secondary_review: boolean;
  clause_library_version?: string | null;
  agent_runs?: AgentRun[];
  input_text?: string;
  created_at?: string;
}

// One selected agent's result within a classification job (for side-by-side
// comparison on the Review screen). Shares the rbi_/sebi_ shape of the job.
export interface AgentRun {
  id: string;
  agent_id: string | null;
  agent_name: string;
  status: string;
  rbi_label: string | null;
  rbi_confidence: number | null;
  rbi_evidence: RegulatorEvidence | null;
  sebi_label: string | null;
  sebi_confidence: number | null;
  sebi_evidence: RegulatorEvidence | null;
  created_at?: string;
}

// A saved, named prompt configuration for M1 classification.
export interface ClassificationAgent {
  id: string;
  name: string;
  description: string | null;
  rbi_prompt: string;
  sebi_prompt: string;
  model_version: string;
  temperature: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface AgentDefaults {
  rbi_prompt: string;
  sebi_prompt: string;
  model_version: string;
  temperature: number;
}

export interface Clause {
  id: string;
  version: string;
  regulator: string;
  clause_ref: string;
  text: string;
  tags: string | null;
  instrument?: string | null;
  source_doc?: string | null;
  page_no?: number | null;
  para_no?: string | null;
}

export interface RegulationDocument {
  id: string;
  regulator: string;
  instrument: string;
  source_doc: string;
  filename: string;
  status: "processing" | "pending_review" | "active" | "archived" | "failed";
  uploaded_by: string | null;
  created_at: string;
  activated_at: string | null;
  archived_at: string | null;
  clause_count: number;
}

export interface Vendor {
  id: string;
  legal_name: string;
  cin: string | null;
  pan: string | null;
  website?: string | null;
  country?: string | null;
}

// Rich vendor due-diligence audit (mirrors backend BLANK_AUDIT). Typed
// loosely on purpose — the model fills what it finds; the UI guards each
// section. See backend/app/adapters/osint/blank_audit.py.
export interface AuditData {
  _url?: string;
  _domain?: string;
  _model_version?: string;
  _error?: string;
  _grounding_sources?: Array<{ title?: string; url: string }>;
  business_name?: string;
  business_description?: string;
  industry?: string;
  country?: string;
  ssl_secure?: boolean;
  mobile_friendly?: boolean;
  key_pages?: Array<{ page: string; status: string; url?: string; snapshot?: string; missing_info?: string[] }>;
  payment?: { gateway?: string; confidence?: string; evidence?: string; methods?: string[]; notes?: string };
  technical?: {
    platform?: string; platform_clues?: string[]; domain_age?: string; domain_registered?: string;
    hosting?: string; analytics?: string[]; marketing_tools?: string[];
    security_headers?: { hsts?: boolean; csp?: boolean; xframe?: boolean }; notes?: string;
  };
  security?: {
    owasp_posture_score?: number;
    vapt_findings?: Array<{ category?: string; severity?: string; description?: string; exploitability?: string; impact?: string; recommendation?: string }>;
    reputation_sources?: Record<string, { detections?: number; status?: string; level?: string; findings?: string }>;
    incident_history?: Array<{ date?: string; event?: string; status?: string; summary?: string }>;
    notes?: string;
  };
  social?: { profiles?: Array<{ platform?: string; url?: string; handle?: string; status?: string; followers?: string }>; reputation?: string; review_summary?: string };
  legal?: {
    news?: Array<{ headline?: string; date?: string; source?: string; url?: string; summary?: string }>;
    litigations?: Array<{ type?: string; status?: string; parties?: string; case_number?: string; court?: string; filing_date?: string; summary?: string }>;
    notes?: string;
  };
  compliance_checks?: Record<string, { status?: string; details?: string; registration_id?: string; registration_type?: string; verification_context?: string }>;
  footprint?: {
    contact_assets?: { emails?: string[]; phones?: string[]; addresses?: string[] };
    discovered_relations?: Array<{ entity_name?: string; url?: string; shared_asset?: string; relationship_type?: string; risk_rating?: string }>;
    discovered_domains?: Array<{ domain?: string; discovery_source?: string; registration_date?: string; status?: string }>;
  };
  verification?: { grounding_score?: number; hallucination_check?: Array<{ data_point?: string; status?: string; evidence_source?: string }> };
  risk?: {
    score?: number; rating?: string; decision?: string; confidence?: string; summary?: string;
    factors?: Array<{ factor?: string; impact?: string; points?: number; detail?: string }>;
    mcc?: { code?: string; description?: string; rationale?: string };
    green_flags?: string[]; red_flags?: string[]; conditions?: string[];
  };
  [key: string]: unknown;
}

export interface DDReport {
  id: string;
  vendor_id: string;
  status: string;
  red_flag_score: number | null;
  weights_version?: string | null;
  outsourcing_checklist: string | null;
  audit_data?: AuditData | null;
  error?: string | null;
  created_at?: string;
  findings: Array<{
    id: string;
    category: string;
    title: string;
    summary: string | null;
    source_tier: string;
    source_url: string | null;
    disposition: string | null;
  }>;
}

export interface Project {
  id: string;
  name: string;
  business_line: string | null;
  intake_data: Record<string, number>;
  status?: string;
}

export interface RiskScore {
  id: string;
  inherent_score: number;
  residual_score: number | null;
  final_inherent_score: number | null;
  final_residual_score: number | null;
  drivers: { top_factors?: Array<{ factor: string; contribution: number }> } | null;
  status: string;
}

export interface FormFieldDef {
  id: string;
  label: string;
  type: string;
  required?: boolean;
  help_text?: string | null;
  placeholder?: string | null;
  options?: string[] | null;
}

export interface FormSectionDef {
  id: string;
  title: string;
  /** Optional intro shown under the section title. */
  description?: string | null;
  fields: FormFieldDef[];
}

export interface FormTemplateSchema {
  /** "How to fill this form" instructions shown above the wizard. */
  description?: string | null;
  sections: FormSectionDef[];
  repeatable_groups?: FormSectionDef[];
}

export interface FormTemplate {
  id: string;
  name: string;
  version: number;
  schema: FormTemplateSchema;
  is_active: boolean;
  created_at: string;
}

export interface FormSubmission {
  id: string;
  assignment_id: string;
  answers: Record<string, unknown>;
  submitted_by: string;
  submitted_at: string;
}

export interface FormAssignment {
  id: string;
  template_id: string;
  assignee_id: string;
  assigned_by_id: string;
  vendor_id: string | null;
  vendor_legal_name: string | null;
  assignee_display_name: string | null;
  classification_job_id: string | null;
  /** Live status of the M1 classification started at submit. */
  classification_status: string | null;
  classification_label: string | null;
  title: string;
  due_at: string | null;
  status: string;
  draft_answers: Record<string, unknown> | null;
  last_reminder_at: string | null;
  created_at: string;
  updated_at: string;
  template?: FormTemplate | null;
  submission?: FormSubmission | null;
}

export interface FormImportResult {
  assignment: FormAssignment;
  imported_count: number;
  unmatched: string[];
  warnings: string[];
}

export interface ExcelSheetPreview {
  index: number;
  name: string;
  row_count: number;
}

export interface ExcelImportPreview {
  sheets: ExcelSheetPreview[];
}

export interface FormAssignmentItemCreate {
  assignee_id: string;
  vendor_id?: string | null;
  vendor_name?: string | null;
}

export interface FormAssignmentBulkCreate {
  template_id: string;
  title: string;
  due_at?: string | null;
  assignments: FormAssignmentItemCreate[];
}
