import type {
  AuditLogEntry,
  ChatAttachment,
  ChatContextRef,
  ChatSessionSummary,
  ChatShareEntry,
  ChatShareResult,
  ChatShareUser,
  ChatTurnOut,
  NotificationSettings,
  Comparison,
  ComparisonSummary,
  Contract,
  ContractRevision,
  ContractRevisionSummary,
  ContractSummary,
  ContractTemplate,
  ContractTemplateSummary,
  DailyBrief,
  DailyCount,
  DailyTokenTrend,
  DocumentVersion,
  EmailDraft,
  FeatureRequest,
  FeatureRequestSummary,
  GmailLabel,
  GmailMessage,
  GmailMessageList,
  GmailMessageSummary,
  GmailPollSummary,
  GmailSettings,
  GmailStatus,
  GmailThread,
  LegalBotQuery,
  MetricsDateRange,
  MetricsSummary,
  MetricsUsersPage,
  ModuleDailyTrend,
  ModuleUsage,
  MSAPromptEditPreview,
  MSAPromptRevisionSummary,
  OnlyOfficeConfig,
  MSASuggestionsPreview,
  MSASummary,
  MSATracker,
  NegotiationChanges,
  NegotiationTask,
  RegulatoryUpdate,
  ResearchNote,
  ResearchSummary,
  Task,
  TaskAggregated,
  TemplateLibraryCategories,
  TemplateLibraryItem,
  TemplateLibraryPreview,
  User,
  UserSegment,
} from "@/types";
import {
  clearSessionMeta,
  setAuthMessage,
} from "@/lib/session";

// Default to same-origin ("") so the SPA calls "/api/..." and the reverse
// proxy (nginx in prod, Vite dev-server proxy locally) forwards to the backend.
// Override with VITE_API_BASE_URL only for a cross-origin API.
const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export type AuthTokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  idle_timeout_seconds?: number;
  absolute_timeout_seconds?: number;
};

// Session lives in an httpOnly cookie the browser attaches automatically —
// no client-readable token, immune to XSS token theft by design. This just
// clears the local, non-sensitive idle/timeout bookkeeping in session.ts.
export function clearSession(): void {
  clearSessionMeta();
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

function handleUnauthorized(path: string, detail: string): void {
  // Don't bounce the login form itself.
  if (path.startsWith("/api/auth/login") || path.startsWith("/api/auth/accept-invite")) {
    return;
  }
  // Don't hard-redirect while an SSO code handoff is in flight — Login.tsx is
  // already exchanging it via a soft route change; a hard reload here would
  // abort that request mid-flight and strand the user on the login page.
  if (typeof window !== "undefined" && new URLSearchParams(window.location.search).has("code")) {
    return;
  }
  // The cookie is invisible to JS, so we can no longer ask "did we ever have
  // a token" — instead trust the server: a bare, generic rejection (no
  // cookie/header presented at all) reads as "never signed in", while any
  // more specific detail (expired, inactive, malformed) implies a real prior
  // session that's now invalid and deserves the "expired" messaging.
  const generic = detail.toLowerCase() === "not authenticated" || detail.toLowerCase() === "unauthorized";
  if (generic) {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
    return;
  }
  setAuthMessage(detail);
  clearSession();
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    const q = new URLSearchParams({ reason: "session" });
    window.location.assign(`/login?${q.toString()}`);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const resp = await fetch(`${BASE}${path}`, { ...init, headers, credentials: "include" });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    if (resp.status === 401) {
      handleUnauthorized(path, typeof detail === "string" ? detail : "Unauthorized");
    }
    throw new ApiError(resp.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

function fileUrl(path: string): string {
  // Same-origin navigation (<a href>, window.open) auto-attaches the cookie —
  // no token needs to ride along in the URL (and land in browser history).
  return `${BASE}${path}`;
}

// ── auth ──────────────────────────────────────────────────────────────────────
export const api = {
  login: (email: string, password: string) =>
    request<AuthTokenResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  keycloakCallback: (code: string, redirect_uri: string) =>
    request<AuthTokenResponse>("/api/auth/keycloak/callback", {
      method: "POST",
      body: JSON.stringify({ code, redirect_uri }),
    }),
  exchangeSSOCode: (code: string) =>
    request<AuthTokenResponse>("/api/auth/exchange-sso-code", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  refreshSession: () =>
    request<AuthTokenResponse>("/api/auth/refresh", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
  logout: () => request<{ message: string }>("/api/auth/logout", { method: "POST" }),
  getConfig: () => request<{ sso_enabled: boolean }>("/api/auth/config"),

  // users
  listUsers: () => request<User[]>("/api/users"),
  syncUsersFromIam: () =>
    request<import("@/types").IamSyncResult>("/api/users/sync", { method: "POST" }),
  createUser: (data: { email: string; password: string; full_name: string; role: string }) =>
    request<User>("/api/users", { method: "POST", body: JSON.stringify(data) }),
  updateUser: (id: number, data: { full_name?: string; role?: string; is_active?: boolean }) =>
    request<User>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  inviteUser: (data: { email: string; full_name: string; role: string }) =>
    request<import("@/types").InviteResult>("/api/users/invite", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  resendInvite: (id: number) =>
    request<import("@/types").InviteResult>(`/api/users/${id}/resend-invite`, { method: "POST" }),
  deleteUser: (id: number) => request<void>(`/api/users/${id}`, { method: "DELETE" }),
  validateInvite: (token: string) =>
    request<import("@/types").InviteTokenInfo>(
      `/api/auth/invite/validate?token=${encodeURIComponent(token)}`,
    ),
  acceptInvite: (token: string, password: string) =>
    request<AuthTokenResponse>("/api/auth/accept-invite", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    }),

  // contract review
  listContracts: () => request<ContractSummary[]>("/api/contract-review"),
  createContract: (data: {
    filename: string;
    contract_type: string;
    raw_text: string;
    review_guidelines?: string | null;
  }) => request<Contract>("/api/contract-review", { method: "POST", body: JSON.stringify(data) }),
  getContract: (id: number) => request<Contract>(`/api/contract-review/${id}`),
  runContractReview: (id: number, data?: { review_guidelines?: string | null }) =>
    request<Contract>(`/api/contract-review/${id}/run-review`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),
  decideContractSuggestion: (
    id: number,
    suggestion_id: number,
    decision: string,
    reviewer_edit?: string,
  ) =>
    request<Contract>(`/api/contract-review/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({ suggestion_id, decision, reviewer_edit }),
    }),
  previewContractSuggestions: (id: number) =>
    request<import("@/types").ContractSuggestionsPreview>(
      `/api/contract-review/${id}/suggestions/preview`,
      { method: "POST" },
    ),
  applyContractSuggestions: (
    id: number,
    data?: { edited_text?: string; change_mode?: string; force?: boolean },
  ) =>
    request<Contract>(`/api/contract-review/${id}/suggestions/apply`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),
  getContractChanges: (id: number) =>
    request<{ change_history: import("@/types").ReviewChangeEntry[] }>(
      `/api/contract-review/${id}/changes`,
    ),
  decideClause: (
    contractId: number,
    clauseId: number,
    data: { decision: string; reviewer_edit?: string; reviewer_comment?: string },
  ) =>
    request<Contract>(`/api/contract-review/${contractId}/clauses/${clauseId}/decision`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  finalizeContract: (id: number) =>
    request<Contract>(`/api/contract-review/${id}/finalize`, { method: "POST" }),
  // prompt-based document editing (track mode)
  promptEditContract: (id: number, data: { instruction: string; selection?: string }) =>
    request<ContractRevision>(`/api/contract-review/${id}/prompt-edit`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listContractRevisions: (id: number) =>
    request<ContractRevisionSummary[]>(`/api/contract-review/${id}/revisions`),
  getContractRevision: (id: number, revisionId: number) =>
    request<ContractRevision>(`/api/contract-review/${id}/revisions/${revisionId}`),
  applyContractRevision: (id: number, revisionId: number) =>
    request<Contract>(`/api/contract-review/${id}/revisions/${revisionId}/apply`, {
      method: "POST",
    }),
  discardContractRevision: (id: number, revisionId: number) =>
    request<ContractRevision>(`/api/contract-review/${id}/revisions/${revisionId}/discard`, {
      method: "POST",
    }),

  // document comparison
  listComparisons: () => request<ComparisonSummary[]>("/api/document-comparison"),
  createComparison: (data: {
    label: string;
    v1_filename: string;
    v2_filename: string;
    v1_text: string;
    v2_text: string;
  }) => request<Comparison>("/api/document-comparison", { method: "POST", body: JSON.stringify(data) }),
  createComparisonUpload: (form: FormData) =>
    request<Comparison>("/api/document-comparison/upload", { method: "POST", body: form }),
  getComparison: (id: number) => request<Comparison>(`/api/document-comparison/${id}`),

  // legal bot
  askBot: (
    question: string,
    context?: {
      context_type?: "none" | "msa_version" | "gmail_thread";
      context_tracker_id?: number;
      context_version_id?: number;
      context_gmail_thread_id?: string;
    },
  ) =>
    request<LegalBotQuery>("/api/legal-bot/ask", {
      method: "POST",
      body: JSON.stringify({ question, ...context }),
    }),
  myQueries: () => request<LegalBotQuery[]>("/api/legal-bot/my-queries"),
  escalatedQueries: () => request<LegalBotQuery[]>("/api/legal-bot/escalated"),

  // chatbot orchestrator (streaming assistant)
  listChatSessions: () => request<ChatSessionSummary[]>("/api/chat/sessions"),
  getChatHistory: (sessionId: string) =>
    request<ChatTurnOut[]>(`/api/chat/sessions/${encodeURIComponent(sessionId)}`),
  uploadChatAttachment: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ChatAttachment>("/api/chat/attachments", { method: "POST", body: form });
  },
  listSharedChats: () => request<ChatSessionSummary[]>("/api/chat/shared"),
  listShareableUsers: () => request<ChatShareUser[]>("/api/chat/users"),

  // notification preferences
  getNotificationSettings: () =>
    request<NotificationSettings>("/api/notifications/settings"),
  updateNotificationSettings: (data: Partial<NotificationSettings>) =>
    request<NotificationSettings>("/api/notifications/settings", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  shareChat: (sessionId: string, emails: string[]) =>
    request<ChatShareResult>(`/api/chat/sessions/${encodeURIComponent(sessionId)}/share`, {
      method: "POST",
      body: JSON.stringify({ emails }),
    }),
  listChatShares: (sessionId: string) =>
    request<ChatShareEntry[]>(
      `/api/chat/sessions/${encodeURIComponent(sessionId)}/shares`,
    ),
  revokeChatShare: (sessionId: string, userId: number) =>
    request<void>(
      `/api/chat/sessions/${encodeURIComponent(sessionId)}/shares/${userId}`,
      { method: "DELETE" },
    ),
  /** Chat-facing JFPSL template list (LEGAL_BOT_USE) — fallback when library 403s. */
  listChatTemplates: () => request<TemplateLibraryItem[]>("/api/chat/templates"),
  /** Attach a library template as a chat attachment (returns AttachmentOut). */
  attachChatTemplate: (storageKey: string) =>
    request<ChatAttachment>("/api/chat/templates", {
      method: "POST",
      body: JSON.stringify({ storage_key: storageKey }),
    }),
  deleteChat: (sessionId: string) =>
    request<void>(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }),
  submitChatFeedback: (
    turnId: number,
    opts: { value?: "up" | "down" | null; comment?: string | null },
  ) => {
    const body: { value?: "up" | "down" | null; comment?: string | null } = {};
    if ("value" in opts) body.value = opts.value ?? null;
    if ("comment" in opts) body.comment = opts.comment ?? null;
    return request<{ turn_id: number; feedback: "up" | "down" | null; comment: string | null }>(
      `/api/chat/turns/${turnId}/feedback`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },
  chatTurnExportUrl: (turnId: number) => fileUrl(`/api/chat/turns/${turnId}/export`),
  chatExportUrl: (sessionId: string) =>
    fileUrl(`/api/chat/sessions/${encodeURIComponent(sessionId)}/export`),
  sendChatTurnToMsa: (turnId: number) =>
    request<{ tracker_id?: number; detail?: string }>(`/api/chat/turns/${turnId}/msa`, {
      method: "POST",
    }),
  overrideQuery: (id: number, legal_override: string) =>
    request<LegalBotQuery>(`/api/legal-bot/${id}/override`, {
      method: "POST",
      body: JSON.stringify({ legal_override }),
    }),

  // legal research
  listResearch: () => request<ResearchSummary[]>("/api/legal-research"),
  createResearch: (query: string) =>
    request<ResearchNote>("/api/legal-research", { method: "POST", body: JSON.stringify({ query }) }),
  getResearch: (id: number) => request<ResearchNote>(`/api/legal-research/${id}`),
  updateResearch: (id: number, data: { reviewer_notes?: string; status?: string }) =>
    request<ResearchNote>(`/api/legal-research/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  // contract templates / GCS library
  listContractTemplates: (contractType?: string) => {
    const qs = contractType ? `?contract_type=${encodeURIComponent(contractType)}` : "";
    return request<ContractTemplateSummary[]>(`/api/contract-templates${qs}`);
  },
  getContractTemplate: (id: number) => request<ContractTemplate>(`/api/contract-templates/${id}`),
  createContractTemplate: (data: {
    contract_type: string;
    name: string;
    description?: string;
    template_text: string;
  }) =>
    request<ContractTemplate>("/api/contract-templates", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateContractTemplate: (
    id: number,
    data: Partial<{ name: string; description: string; template_text: string; is_active: boolean }>,
  ) =>
    request<ContractTemplate>(`/api/contract-templates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  listTemplateLibrary: (params?: { doc_kind?: string; contract_type?: string }) => {
    const qs = new URLSearchParams();
    if (params?.doc_kind) qs.set("doc_kind", params.doc_kind);
    if (params?.contract_type) qs.set("contract_type", params.contract_type);
    const q = qs.toString();
    return request<TemplateLibraryItem[]>(`/api/contract-templates/library${q ? `?${q}` : ""}`);
  },
  templateLibraryCategories: () =>
    request<TemplateLibraryCategories>("/api/contract-templates/library/categories"),
  previewTemplateLibrary: (storageKey: string) =>
    request<TemplateLibraryPreview>(
      `/api/contract-templates/library/preview?storage_key=${encodeURIComponent(storageKey)}`,
    ),
  /** Authenticated URL for the original library binary (PDF/DOCX) used by DocumentViewer. */
  libraryFileUrl: (storageKey: string) =>
    fileUrl(
      `/api/contract-templates/library/file?storage_key=${encodeURIComponent(storageKey)}`,
    ),
  uploadTemplateLibrary: (form: FormData) =>
    request<TemplateLibraryItem>("/api/contract-templates/library/upload", {
      method: "POST",
      body: form,
    }),

  // gmail
  gmailStatus: () => request<GmailStatus>("/api/gmail/status"),
  gmailSettings: () => request<GmailSettings>("/api/gmail/settings"),
  updateGmailSettings: (
    data: Partial<
      Pick<
        GmailSettings,
        | "poll_enabled"
        | "poll_labels"
        | "auto_task_ingest"
        | "poll_lookback_days"
        | "watched_threads"
        | "watched_senders"
        | "default_context_module"
      >
    >,
  ) => request<GmailSettings>("/api/gmail/settings", { method: "PATCH", body: JSON.stringify(data) }),
  gmailLabels: () => request<GmailLabel[]>("/api/gmail/labels"),
  gmailMessages: (params?: {
    subject?: string;
    label?: string;
    from_addr?: string;
    q?: string;
    newer_than_days?: number;
    max_results?: number;
    page_token?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.subject) qs.set("subject", params.subject);
    if (params?.label) qs.set("label", params.label);
    if (params?.from_addr) qs.set("from_addr", params.from_addr);
    if (params?.q) qs.set("q", params.q);
    if (params?.newer_than_days) qs.set("newer_than_days", String(params.newer_than_days));
    if (params?.max_results) qs.set("max_results", String(params.max_results));
    if (params?.page_token) qs.set("page_token", params.page_token);
    const q = qs.toString();
    return request<GmailMessageList>(`/api/gmail/messages${q ? `?${q}` : ""}`);
  },
  gmailMessage: (id: string) => request<GmailMessage>(`/api/gmail/messages/${id}`),
  gmailThread: (threadId: string) => request<GmailThread>(`/api/gmail/threads/${threadId}`),
  gmailOAuthStart: (returnTo = "tasks") =>
    request<{ authorization_url: string; state: string }>(`/api/gmail/oauth/start?return_to=${returnTo}`),
  pollGmail: (forceIngest = true, msaOnly = false) =>
    request<GmailPollSummary>(
      `/api/gmail/poll?force_ingest=${forceIngest ? "true" : "false"}&msa_only=${msaOnly ? "true" : "false"}`,
      { method: "POST" },
    ),
  watchGmailThread: (data: { thread_id: string; subject?: string; from_addr?: string }) =>
    request<GmailSettings>("/api/gmail/watches/threads", { method: "POST", body: JSON.stringify(data) }),
  unwatchGmailThread: (threadId: string) =>
    request<GmailSettings>(`/api/gmail/watches/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" }),
  watchGmailSender: (email: string) =>
    request<GmailSettings>("/api/gmail/watches/senders", { method: "POST", body: JSON.stringify({ email }) }),
  unwatchGmailSender: (email: string) =>
    request<GmailSettings>(`/api/gmail/watches/senders/${encodeURIComponent(email)}`, { method: "DELETE" }),
  ingestGmailMessageTasks: (messageId: string) =>
    request<{ count: number; task_ids: number[]; reason?: string }>(
      `/api/gmail/messages/${messageId}/ingest-tasks`,
      { method: "POST" },
    ),
  listEmailDrafts: (status?: string) =>
    request<EmailDraft[]>(`/api/gmail/drafts${status ? `?status=${status}` : ""}`),
  getEmailDraft: (id: number) => request<EmailDraft>(`/api/gmail/drafts/${id}`),
  createEmailDraft: (data: { gmail_thread_id: string; gmail_message_id: string; user_feedback?: string }) =>
    request<EmailDraft>("/api/gmail/drafts", { method: "POST", body: JSON.stringify(data) }),
  updateEmailDraft: (id: number, data: Partial<{ draft_subject: string; draft_body: string; user_feedback: string; status: string }>) =>
    request<EmailDraft>(`/api/gmail/drafts/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  regenerateEmailDraft: (id: number) =>
    request<EmailDraft>(`/api/gmail/drafts/${id}/regenerate`, { method: "POST" }),
  approveEmailDraft: (id: number, remindInHours = 2) =>
    request<EmailDraft>(`/api/gmail/drafts/${id}/approve`, { method: "POST", body: JSON.stringify({ remind_in_hours: remindInHours }) }),
  sendEmailDraft: (id: number) =>
    request<EmailDraft>(`/api/gmail/drafts/${id}/send`, { method: "POST" }),
  dismissEmailDraft: (id: number) =>
    request<EmailDraft>(`/api/gmail/drafts/${id}/dismiss`, { method: "POST" }),

  // msa
  listMSA: () => request<MSASummary[]>("/api/msa"),
  startMSA: (data: {
    vendor_name: string;
    vendor_email: string;
    contract_type: string;
    skip_ai_review?: boolean;
    template_id?: number | null;
    base_text?: string | null;
    review_guidelines?: string | null;
  }) => request<MSATracker>("/api/msa/start", { method: "POST", body: JSON.stringify(data) }),
  startMSAUpload: (form: FormData) =>
    request<MSATracker>("/api/msa/start/upload", { method: "POST", body: form }),
  listMSAVersions: (trackerId: number) =>
    request<DocumentVersion[]>(`/api/msa/${trackerId}/versions`),
  getMSAVersionText: (trackerId: number, versionId: number) =>
    request<{ version_id: number; extracted_text: string }>(
      `/api/msa/${trackerId}/versions/${versionId}/text`,
    ),
  getMSAOnlyOfficeConfig: (trackerId: number, versionId: number, mode: "edit" | "view" = "edit") =>
    request<OnlyOfficeConfig>(
      `/api/msa/${trackerId}/versions/${versionId}/onlyoffice-config?mode=${mode}`,
    ),
  saveMSAOnlyOfficeVersion: (trackerId: number, versionId: number) =>
    request<{ accepted: boolean; error_code: number }>(
      `/api/msa/${trackerId}/versions/${versionId}/onlyoffice-save`,
      { method: "POST" },
    ),
  uploadMSAVersion: (trackerId: number, form: FormData) =>
    request<DocumentVersion>(`/api/msa/${trackerId}/versions`, { method: "POST", body: form }),
  promptEditMSA: (
    trackerId: number,
    data: { instruction: string; selection?: string; base_version_id?: number; review_guidelines?: string },
  ) =>
    request<MSAPromptEditPreview>(`/api/msa/${trackerId}/prompt-edit`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  applyMSAPromptEdit: (
    trackerId: number,
    data: {
      instruction: string;
      edited_text?: string;
      parent_version_id: number;
      revision_id?: number;
      operations?: import("@/types").MSADocxOperation[];
    },
  ) =>
    request<MSATracker>(`/api/msa/${trackerId}/prompt-edit/apply`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listMSAPromptRevisions: (trackerId: number) =>
    request<MSAPromptRevisionSummary[]>(`/api/msa/${trackerId}/prompt-revisions`),
  getMSAPromptRevision: (trackerId: number, revisionId: number) =>
    request<import("@/types").MSAPromptRevision>(
      `/api/msa/${trackerId}/prompt-revisions/${revisionId}`,
    ),
  discardMSAPromptRevision: (trackerId: number, revisionId: number) =>
    request<MSAPromptRevisionSummary>(`/api/msa/${trackerId}/prompt-revisions/${revisionId}/discard`, {
      method: "POST",
    }),
  deleteMSAPromptRevision: (trackerId: number, revisionId: number) =>
    request<void>(`/api/msa/${trackerId}/prompt-revisions/${revisionId}`, {
      method: "DELETE",
    }),
  previewMSASuggestions: (trackerId: number) =>
    request<MSASuggestionsPreview>(`/api/msa/${trackerId}/suggestions/preview`, {
      method: "POST",
    }),
  applyMSASuggestions: (
    trackerId: number,
    data: { parent_version_id: number; edited_text?: string; force?: boolean; change_mode?: string },
  ) =>
    request<MSATracker>(`/api/msa/${trackerId}/suggestions/apply`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  applyMSAHumanEdit: (
    trackerId: number,
    data: { parent_version_id: number; edited_text: string; rich_html?: string },
  ) =>
    request<MSATracker>(`/api/msa/${trackerId}/human-edit/apply`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getMSAChanges: (trackerId: number) => request<NegotiationChanges>(`/api/msa/${trackerId}/changes`),
  compareMSAVersions: (trackerId: number, from_version_id: number, to_version_id: number) =>
    request<NegotiationChanges>(
      `/api/msa/${trackerId}/compare?from_version_id=${from_version_id}&to_version_id=${to_version_id}`,
      { method: "POST" },
    ),
  listMSATasks: (trackerId: number, status?: string, includeLow?: boolean) => {
    const qs = new URLSearchParams();
    if (status) qs.set("status_filter", status);
    if (includeLow) qs.set("include_low", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<NegotiationTask[]>(`/api/msa/${trackerId}/tasks${suffix}`);
  },
  promoteMSATask: (trackerId: number, taskId: number) =>
    request<Task>(`/api/msa/${trackerId}/tasks/${taskId}/promote`, { method: "POST" }),
  listMSAMemory: (trackerId: number) =>
    request<import("@/types").NegotiationMemoryEntry[]>(`/api/msa/${trackerId}/memory`),
  getMSAReviewHistory: (trackerId: number) =>
    request<{ change_history: import("@/types").ReviewChangeEntry[] }>(
      `/api/msa/${trackerId}/review-history`,
    ),
  updateMSATask: (trackerId: number, taskId: number, data: { status?: string; assigned_to_id?: number }) =>
    request<NegotiationTask>(`/api/msa/${trackerId}/tasks/${taskId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  finalizeMSA: (trackerId: number) =>
    request<MSATracker>(`/api/msa/${trackerId}/finalize`, { method: "POST" }),
  msaFileUrl: (storageKey: string) => fileUrl(`/api/msa/files/${storageKey}`),
  ingestMSA: (data: {
    vendor_name: string;
    vendor_email: string;
    contract_type: string;
    subject: string;
    body: string;
    attachment_name: string;
    attachment_text: string;
  }) => request<MSATracker>("/api/msa/ingest", { method: "POST", body: JSON.stringify(data) }),
  runMSAReview: (
    trackerId: number,
    data?: { version_id?: number; review_guidelines?: string | null },
  ) =>
    request<MSATracker>(`/api/msa/${trackerId}/run-review`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    }),
  decideAllMSASuggestions: (trackerId: number, decision: "accept" | "reject" = "accept") =>
    request<MSATracker>(`/api/msa/${trackerId}/suggestions/decide-all`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
  listMSAShares: (trackerId: number) => request<import("@/types").MSAShare[]>(`/api/msa/${trackerId}/shares`),
  createMSAShare: (trackerId: number, data: { user_id: number; access_level: "view" | "edit" }) =>
    request<import("@/types").MSAShare>(`/api/msa/${trackerId}/shares`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  revokeMSAShare: (trackerId: number, userId: number) =>
    request<void>(`/api/msa/${trackerId}/shares/${userId}`, { method: "DELETE" }),
  searchShareableUsers: (q: string) =>
    request<import("@/types").ShareableUser[]>(
      `/api/msa/shareable-users?q=${encodeURIComponent(q)}`,
    ),
  getMSA: (id: number) => request<MSATracker>(`/api/msa/${id}`),
  decideMSA: (id: number, suggestion_id: number, decision: string, reviewer_edit?: string) =>
    request<MSATracker>(`/api/msa/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({ suggestion_id, decision, reviewer_edit }),
    }),
  sendMSA: (id: number, subject: string, body: string) =>
    request<MSATracker>(`/api/msa/${id}/send`, {
      method: "POST",
      body: JSON.stringify({ subject, body }),
    }),
  listMSAGmailWatches: () => request<import("@/types").MSAGmailWatch[]>("/api/msa/gmail/watches"),
  watchMSAGmailThread: (data: { thread_id: string; subject?: string; vendor_email?: string }) =>
    request<import("@/types").MSAGmailWatch[]>("/api/msa/gmail/watch", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  linkMSAGmailThread: (
    trackerId: number,
    data: { thread_id: string; subject?: string; vendor_email?: string },
  ) =>
    request<MSATracker>(`/api/msa/${trackerId}/gmail/watch`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  unlinkMSAGmailThread: (trackerId: number) =>
    request<MSATracker>(`/api/msa/${trackerId}/gmail/watch`, { method: "DELETE" }),

  // legal news / regulatory intelligence
  listNews: (
    params: {
      source?: string;
      status?: string;
      regulator?: string;
      category?: string;
      q?: string;
      days?: number;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.source) qs.set("source", params.source);
    if (params.status) qs.set("status", params.status);
    if (params.regulator) qs.set("regulator", params.regulator);
    if (params.category) qs.set("category", params.category);
    if (params.q) qs.set("q", params.q);
    if (params.days) qs.set("days", String(params.days));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<RegulatoryUpdate[]>(`/api/legal-news${suffix}`);
  },
  newsOverview: () => request<import("@/types").NewsOverview>("/api/legal-news/overview"),
  listSources: () => request<import("@/types").TrackedSource[]>("/api/legal-news/sources"),
  createSource: (data: {
    name: string;
    url: string;
    regulator: string;
    category: string;
    source_type?: string;
  }) =>
    request<import("@/types").TrackedSource>("/api/legal-news/sources", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateSource: (id: number, data: Partial<import("@/types").TrackedSource>) =>
    request<import("@/types").TrackedSource>(`/api/legal-news/sources/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteSource: (id: number) =>
    request<void>(`/api/legal-news/sources/${id}`, { method: "DELETE" }),

  // regulatory knowledge corpus (statutes / master directions / circulars)
  corpusOverview: () =>
    request<import("@/types").CorpusOverview>("/api/regulatory-corpus"),
  uploadCorpusDocument: (docId: string, form: FormData, force = false) =>
    request<import("@/types").CorpusIngestResult>(
      `/api/regulatory-corpus/${encodeURIComponent(docId)}/upload?force=${force}`,
      { method: "POST", body: form },
    ),
  fetchCorpusDocument: (docId: string, force = false) =>
    request<import("@/types").CorpusIngestResult>(
      `/api/regulatory-corpus/${encodeURIComponent(docId)}/fetch?force=${force}`,
      { method: "POST" },
    ),
  corpusChunks: (docId: string, limit = 50) =>
    request<import("@/types").CorpusChunk[]>(
      `/api/regulatory-corpus/${encodeURIComponent(docId)}/chunks?limit=${limit}`,
    ),
  deleteCorpusDocument: (docId: string) =>
    request<void>(`/api/regulatory-corpus/${encodeURIComponent(docId)}`, {
      method: "DELETE",
    }),
  refreshCorpusSupersession: () =>
    request<{ reindexed: number }>("/api/regulatory-corpus/supersession", {
      method: "POST",
    }),
  refreshNews: () =>
    request<import("@/types").RefreshSummary>("/api/legal-news/refresh", { method: "POST" }),
  refreshSource: (id: number) =>
    request<import("@/types").RefreshSummary>(`/api/legal-news/sources/${id}/refresh`, {
      method: "POST",
    }),
  discoverNews: (q: string) =>
    request<import("@/types").DiscoverResult[]>(
      `/api/legal-news/discover?q=${encodeURIComponent(q)}`,
    ),
  saveDiscovered: (data: { url: string; title: string; regulator?: string; category?: string }) =>
    request<RegulatoryUpdate>("/api/legal-news/discover/save", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  ingestNews: (data: {
    source: string;
    title: string;
    full_text: string;
    url?: string;
    published_at: string;
  }) => request<RegulatoryUpdate>("/api/legal-news/ingest", { method: "POST", body: JSON.stringify(data) }),
  triageNews: (id: number, status: string, impact_note?: string) =>
    request<RegulatoryUpdate>(`/api/legal-news/${id}/triage`, {
      method: "POST",
      body: JSON.stringify({ status, impact_note }),
    }),

  // tasks
  dailyBrief: () => request<DailyBrief>("/api/tasks/daily-brief"),
  listTasks: (params: {
    status?: string;
    priority?: string;
    due?: string;
    sources?: string[];
    gmailOnly?: boolean;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.priority) qs.set("priority", params.priority);
    if (params.due) qs.set("due", params.due);
    if (params.sources?.length) {
      params.sources.forEach((s) => qs.append("sources", s));
    }
    if (params.gmailOnly) qs.set("gmail_only", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<Task[]>(`/api/tasks${suffix}`);
  },
  createTask: (data: {
    title: string;
    description?: string;
    priority?: string;
    due_date?: string | null;
    estimated_minutes?: number | null;
    tags?: string[];
    assigned_to_id?: number | null;
  }) => request<Task>("/api/tasks", { method: "POST", body: JSON.stringify(data) }),
  ingestEmailTasks: (data: {
    sender_name: string;
    sender_email: string;
    subject: string;
    body: string;
  }) => request<Task[]>("/api/tasks/ingest-email", { method: "POST", body: JSON.stringify(data) }),
  updateTask: (
    id: number,
    data: Partial<{
      title: string;
      description: string;
      priority: string;
      status: string;
      due_date: string | null;
      estimated_minutes: number | null;
      tags: string[];
      assigned_to_id: number | null;
    }>,
  ) => request<Task>(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  snoozeTask: (id: number, snoozed_until: string) =>
    request<Task>(`/api/tasks/${id}/snooze`, {
      method: "POST",
      body: JSON.stringify({ snoozed_until }),
    }),
  deleteTask: (id: number) => request<void>(`/api/tasks/${id}`, { method: "DELETE" }),
  promoteAggregated: (key: string) =>
    request<Task>(`/api/tasks/promote?key=${encodeURIComponent(key)}`, { method: "POST" }),
  aggregatedTasks: () => request<TaskAggregated[]>("/api/tasks/aggregate"),

  // build studio
  listFeatureRequests: () => request<FeatureRequestSummary[]>("/api/build-studio"),
  getFeatureRequest: (id: number) => request<FeatureRequest>(`/api/build-studio/${id}`),
  submitFeatureRequest: (data: {
    title: string;
    description: string;
    request_type: string;
    priority?: string;
    repository?: string;
  }) =>
    request<FeatureRequest>("/api/build-studio", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  approvePR: (id: number) =>
    request<FeatureRequest>(`/api/build-studio/${id}/approve-pr`, { method: "POST" }),
  rejectFeatureRequest: (id: number, reason: string) =>
    request<FeatureRequest>(
      `/api/build-studio/${id}/reject?reason=${encodeURIComponent(reason)}`,
      { method: "POST" },
    ),

  // playbook & clause bank
  listPlaybookClauses: (contractType?: string) => {
    const qs = contractType ? `?contract_type=${encodeURIComponent(contractType)}` : "";
    return request<import("@/types").PlaybookClause[]>(`/api/playbook/clauses${qs}`);
  },
  getPlaybookSummary: (contractType: string) =>
    request<import("@/types").PlaybookSummary>(`/api/playbook/summary/${contractType}`),
  createPlaybookClause: (data: Partial<import("@/types").PlaybookClause>) =>
    request<import("@/types").PlaybookClause>("/api/playbook/clauses", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updatePlaybookClause: (id: number, data: Partial<import("@/types").PlaybookClause>) =>
    request<import("@/types").PlaybookClause>(`/api/playbook/clauses/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deletePlaybookClause: (id: number) =>
    request<void>(`/api/playbook/clauses/${id}`, { method: "DELETE" }),
  listClauseBank: (contractType?: string) => {
    const qs = contractType ? `?contract_type=${encodeURIComponent(contractType)}` : "";
    return request<import("@/types").ClauseBankEntry[]>(`/api/clause-bank${qs}`);
  },
  listClauseBankByType: (contractType: string) =>
    request<import("@/types").ClauseBankEntry[]>(`/api/clause-bank/by-contract-type/${contractType}`),
  createClauseBankEntry: (data: Partial<import("@/types").ClauseBankEntry>) =>
    request<import("@/types").ClauseBankEntry>("/api/clause-bank", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateClauseBankEntry: (id: number, data: Partial<import("@/types").ClauseBankEntry>) =>
    request<import("@/types").ClauseBankEntry>(`/api/clause-bank/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteClauseBankEntry: (id: number) =>
    request<void>(`/api/clause-bank/${id}`, { method: "DELETE" }),

  // audit
  listAudit: (params: { module?: string; action_type?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.module) qs.set("module", params.module);
    if (params.action_type) qs.set("action_type", params.action_type);
    if (params.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<AuditLogEntry[]>(`/api/audit${suffix}`);
  },

  // metrics (admin)
  getMetricsSummary: (range: MetricsDateRange = {}) => {
    const qs = metricsQuery(range);
    return request<MetricsSummary>(`/api/metrics/summary${qs}`);
  },
  getMetricsLoginActivity: (range: MetricsDateRange = {}) => {
    const qs = metricsQuery(range);
    return request<DailyCount[]>(`/api/metrics/login-activity${qs}`);
  },
  getMetricsUsageTrend: (range: MetricsDateRange = {}) => {
    const qs = metricsQuery(range);
    return request<ModuleDailyTrend[]>(`/api/metrics/usage-trend${qs}`);
  },
  getMetricsDocumentsTrend: (range: MetricsDateRange = {}) => {
    const qs = metricsQuery(range);
    return request<DailyCount[]>(`/api/metrics/documents-trend${qs}`);
  },
  getMetricsTokenTrend: (range: MetricsDateRange = {}) => {
    const qs = metricsQuery(range);
    return request<DailyTokenTrend[]>(`/api/metrics/token-trend${qs}`);
  },
  getMetricsUserSegments: (range: MetricsDateRange = {}) => {
    const qs = metricsQuery(range);
    return request<UserSegment[]>(`/api/metrics/user-segments${qs}`);
  },
  getMetricsModuleUsage: (range: MetricsDateRange = {}) => {
    const qs = metricsQuery(range);
    return request<ModuleUsage[]>(`/api/metrics/module-usage${qs}`);
  },
  getMetricsChatFeedback: (range: MetricsDateRange = {}) => {
    const qs = metricsQuery(range);
    return request<{
      up: number;
      down: number;
      commented: number;
      total_rated: number;
      recent: Array<{
        turn_id: number;
        mode?: string | null;
        feedback?: "up" | "down" | null;
        comment?: string | null;
        query?: string;
        created_at?: string | null;
      }>;
    }>(`/api/metrics/chat-feedback${qs}`);
  },
  getMetricsUsers: (
    range: MetricsDateRange = {},
    params: { search?: string; page?: number; page_size?: number } = {},
  ) => {
    const qs = metricsQuery(range, params);
    return request<MetricsUsersPage>(`/api/metrics/users${qs}`);
  },
  downloadMetricsUsersCsv: async (range: MetricsDateRange = {}, search?: string) => {
    const qs = metricsQuery(range, { search });
    const resp = await fetch(`${BASE}/api/metrics/users/export${qs}`, { credentials: "include" });
    if (!resp.ok) {
      throw new ApiError(resp.status, resp.statusText);
    }
    return resp.text();
  },
};

// ── chat SSE streaming ──────────────────────────────────────────────────────
// EventSource can't POST, so we stream the response body of a POST and parse the
// SSE frames ourselves (matches .claude/chatbot_skills/sse-events.md).
export interface ChatStreamBody {
  text: string;
  session_id?: string | null;
  context?: ChatContextRef[];
  generate_headline?: boolean;
  mode?: "review" | "research" | "draft";
}

export interface ChatStreamHandlers {
  onThinking?: (text: string) => void;
  onThought?: (thought: import("@/types").ChatThought) => void;
  onPartial?: (text: string, sessionId: string) => void;
  onFinal?: (
    text: string,
    sessionId: string,
    opts: {
      blocked?: boolean;
      headline?: string;
      sources?: import("@/types").ChatSource[];
      thoughts?: import("@/types").ChatThought[];
      turnId?: number | null;
    },
  ) => void;
  onError?: (message: string) => void;
}

export async function streamChat(
  body: ChatStreamBody,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  let resp: Response;
  try {
    resp = await fetch(`${BASE}/api/chat/sse`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") return;
    handlers.onError?.("Network error contacting the assistant.");
    return;
  }

  if (!resp.ok || !resp.body) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail || detail;
    } catch {
      /* ignore */
    }
    if (resp.status === 401) {
      handleUnauthorized(
        "/api/chat/sse",
        typeof detail === "string" ? detail : "Unauthorized",
      );
    }
    handlers.onError?.(typeof detail === "string" ? detail : "Request failed");
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const rawFrame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);

        let eventName = "message";
        let dataStr = "";
        for (const line of rawFrame.split("\n")) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
        }
        if (!dataStr) continue;

        if (eventName === "error") {
          try {
            handlers.onError?.(JSON.parse(dataStr).error);
          } catch {
            handlers.onError?.(dataStr);
          }
          continue;
        }
        try {
          const p = JSON.parse(dataStr) as {
            type?: string;
            text?: string;
            partial?: boolean;
            session_id?: string;
            blocked?: boolean;
            headline?: string;
            sources?: import("@/types").ChatSource[];
            thoughts?: import("@/types").ChatThought[];
            turn_id?: number | null;
            id?: string;
            kind?: import("@/types").ChatThought["kind"];
            title?: string;
            detail?: string | null;
            items?: import("@/types").ChatThoughtItem[];
          };
          if (p.type === "thinking") handlers.onThinking?.(p.text ?? "");
          else if (p.type === "thought" && p.id && p.kind)
            handlers.onThought?.({
              id: p.id,
              kind: p.kind,
              title: p.title ?? "Thinking",
              detail: p.detail ?? null,
              items: p.items ?? [],
            });
          else if (p.partial === true) handlers.onPartial?.(p.text ?? "", p.session_id ?? "");
          else if (p.partial === false)
            handlers.onFinal?.(p.text ?? "", p.session_id ?? "", {
              blocked: p.blocked,
              headline: p.headline,
              sources: p.sources,
              thoughts: p.thoughts,
              turnId: p.turn_id,
            });
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  } catch (err) {
    if ((err as Error)?.name === "AbortError") {
      try {
        await reader.cancel();
      } catch {
        /* ignore */
      }
      return;
    }
    handlers.onError?.("The response stream was interrupted.");
  }
}

function metricsQuery(
  range: MetricsDateRange,
  extra: { search?: string; page?: number; page_size?: number } = {},
): string {
  const qs = new URLSearchParams();
  if (range.start_date) qs.set("start_date", range.start_date);
  if (range.end_date) qs.set("end_date", range.end_date);
  if (extra.search) qs.set("search", extra.search);
  if (extra.page) qs.set("page", String(extra.page));
  if (extra.page_size) qs.set("page_size", String(extra.page_size));
  const s = qs.toString();
  return s ? `?${s}` : "";
}
