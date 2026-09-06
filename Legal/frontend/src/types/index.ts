export type Role =
  | "super_admin"
  | "legal_admin"
  | "legal_user"
  | "business_user"
  | "read_only";

export type Permission =
  | "contract_review"
  | "document_comparison"
  | "legal_bot_use"
  | "legal_research"
  | "msa_automation"
  | "msa_shared_view"
  | "legal_news_full"
  | "legal_news_digest"
  | "user_management"
  | "playbook_management"
  | "audit_log_all"
  | "audit_log_own"
  | "approve_ai_output"
  | "send_email"
  | "task_management"
  | "build_requests"
  | "build_pr_approve";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  iam_managed?: boolean;
  iam_synced_at?: string | null;
  created_at: string;
  last_login_at: string | null;
  permissions: Permission[];
}

export interface IamSyncResult {
  created: number;
  updated: number;
  deactivated: number;
  unchanged: number;
}

export interface ReviewFinding {
  order_index: number;
  heading: string | null;
  clause_text: string;
  risk_flag: string;
  confidence: number;
  rationale: string;
  ai_suggestion: string | null;
  original_text?: string | null;
  proposed_text?: string | null;
  category?: string;
  decision: "pending" | "accept" | "modify" | "reject" | "accepted" | "rejected" | "edited";
  reviewer_edit?: string | null;
  playbook_clause_id?: number | null;
  playbook_clause_type?: string | null;
  standard_position_excerpt?: string | null;
  clause_bank_id?: number | null;
  regulatory_ref?: string | null;
  insert_anchor_hint?: string | null;
}

export interface ReviewChangeEntry {
  source: string;
  status: string;
  before?: string | null;
  after?: string | null;
  rationale?: string | null;
  playbook_clause_id?: number | null;
  decided_by_id?: number | null;
  order_index?: number | null;
  applied_at?: string | null;
}

export interface PlaybookSummary {
  contract_type: string;
  clause_count: number;
  required_count: number;
}

export interface PlaybookClause {
  id: number;
  clause_type: string;
  contract_type: string;
  standard_position: string;
  risk_keywords: string[];
  fallback_text: string | null;
  regulatory_tags: string[];
  is_required: boolean;
  insert_anchor_hint: string | null;
  notes: string | null;
  created_at: string;
}

export interface ClauseBankEntry {
  id: number;
  playbook_clause_id: number | null;
  contract_type: string;
  clause_type: string;
  tier: string;
  title: string;
  body_text: string;
  version: number;
  is_active: boolean;
  regulatory_refs: string[];
  created_at: string;
}

export interface ContractSuggestionsPreview {
  base_text: string;
  edited_text: string;
  diff_blocks: DiffBlock[];
  applied_count: number;
  blocked_count: number;
  accepted_count: number;
  applied: ReviewFinding[];
  blocked: ReviewFinding[];
}

export interface ContractClause {
  id: number;
  order_index: number;
  heading: string | null;
  clause_text: string;
  risk_flag: "high" | "medium" | "low" | "none";
  confidence: number;
  ai_rationale: string | null;
  ai_suggestion: string | null;
  decision: "pending" | "accepted" | "rejected" | "edited";
  reviewer_edit: string | null;
  reviewer_comment: string | null;
  references: Array<Record<string, unknown>> | null;
}

export interface Contract {
  id: number;
  filename: string;
  contract_type: string;
  raw_text: string;
  risk_score: number | null;
  status: string;
  model_version: string | null;
  uploaded_by_id: number;
  reviewed_by_id: number | null;
  created_at: string;
  reviewed_at: string | null;
  review_guidelines?: string | null;
  ai_suggestions?: ReviewFinding[] | null;
  change_history?: ReviewChangeEntry[] | null;
  risk_breakdown?: MSARiskBreakdown | null;
  playbook_summary?: PlaybookSummary | null;
  clauses: ContractClause[];
}

export interface ContractSummary {
  id: number;
  filename: string;
  contract_type: string;
  risk_score: number | null;
  status: string;
  created_at: string;
}

export interface DiffToken {
  text: string;
  op: "equal" | "insert" | "delete";
}

export interface DiffBlock {
  kind: "equal" | "insert" | "delete" | "replace";
  v1: string;
  v2: string;
  // Word-level breakdown, present for "replace" blocks (null otherwise).
  v1_tokens?: DiffToken[] | null;
  v2_tokens?: DiffToken[] | null;
}

export interface EditChange {
  description: string;
  original: string;
  revised: string;
}

export interface ContractRevision {
  id: number;
  contract_id: number;
  instruction: string;
  selection: string | null;
  base_text: string;
  edited_text: string;
  change_summary: string | null;
  changes: EditChange[] | null;
  diff_blocks: DiffBlock[] | null;
  status: "proposed" | "applied" | "discarded";
  model_version: string | null;
  created_by_id: number;
  created_at: string;
  applied_at: string | null;
}

export interface ContractRevisionSummary {
  id: number;
  instruction: string;
  change_summary: string | null;
  status: "proposed" | "applied" | "discarded";
  created_at: string;
  applied_at: string | null;
}

export interface RiskFlag {
  severity: string;
  excerpt: string;
  rationale: string;
}

export interface Comparison {
  id: number;
  label: string;
  v1_filename: string;
  v2_filename: string;
  diff_blocks: DiffBlock[];
  risk_commentary: RiskFlag[];
  summary_report: string;
  model_version: string | null;
  created_at: string;
}

export interface ComparisonSummary {
  id: number;
  label: string;
  v1_filename: string;
  v2_filename: string;
  created_at: string;
}

// ── LawGenie chatbot orchestrator ───────────────────────────────────────────
export interface ChatContextRef {
  kind: "msa_version" | "gmail_thread" | "attachment" | "kb_entry";
  tracker_id?: number;
  version_id?: number;
  gmail_thread_id?: string;
  attachment_id?: string;
  kb_entry_id?: number;
  label?: string;
}

export interface ChatSessionSummary {
  session_id: string;
  title: string;
  last_message_preview: string | null;
  turn_count: number;
  updated_at: string | null;
  shared_by?: string | null;
}

export interface ChatShareResult {
  shared_with: string[];
  not_found: string[];
}

export interface ChatShareUser {
  id: number;
  email: string;
  full_name: string;
  role: string;
}

/** Existing share on a chat session (for the Share modal revoke list). */
export interface ChatShareEntry {
  user_id: number;
  email: string;
  full_name: string;
  shared_at?: string | null;
}

export interface InviteResult {
  user: User;
  email_sent: boolean;
  detail: string;
}

export interface InviteTokenInfo {
  valid: boolean;
  email: string | null;
  full_name: string | null;
  detail: string | null;
}

export interface NotificationSettings {
  email_enabled: boolean;
  chat_share: boolean;
  msa_share: boolean;
  task_assigned: boolean;
  approvals: boolean;
  msa_updates: boolean;
  regulatory: boolean;
}

export interface ChatSource {
  kind: "web" | "template" | "executed" | "attachment" | "regulation";
  title: string;
  url?: string | null;
  snippet?: string | null;
  site?: string | null;
  /** GCS path under legal_templates/, contracts/ or regulatory/ for the preview pane. */
  storage_key?: string | null;
  /** 1-indexed page in the source document when known. */
  page?: number | null;
  /** Stable chunk id so multi-hit docs stay separate cites. */
  chunk_id?: string | null;
  /** Fuller verbatim excerpt for Evidence highlight (falls back to snippet). */
  chunk_text?: string | null;
  attachment_id?: string | null;
  label?: string | null;
  /** Regulatory clause provenance (kind === "regulation"). */
  doc_id?: string | null;
  /** Provision label ("Para 5.3", "Section 43A") — shown instead of "Page N". */
  section_label?: string | null;
  issuer?: string | null;
  effective_date?: string | null;
  superseded_by?: string | null;
  canonical_url?: string | null;
}

/** Ingestion state of one regulatory manifest document. */
export type CorpusDocStatus = "missing" | "ingested" | "stale" | "failed";

export interface CorpusDoc {
  doc_id: string;
  title: string;
  issuer: string;
  domain: string;
  doc_type: string;
  priority: string;
  update_cadence: string;
  download_mode: string;
  official_url?: string | null;
  direct_pdf_url?: string | null;
  version_or_effective: string;
  effective_date?: string | null;
  status: CorpusDocStatus;
  chunk_count: number;
  page_count: number;
  ingested_at?: string | null;
  superseded_by?: string | null;
  supersedes: string[];
  tags: string[];
  storage_key?: string | null;
  last_error?: string | null;
  can_auto_fetch: boolean;
}

export interface CorpusTotals {
  manifest_total: number;
  ingested: number;
  chunks: number;
}

export interface CorpusOverview {
  totals: CorpusTotals;
  documents: CorpusDoc[];
}

export interface CorpusIngestResult {
  doc_id: string;
  status: string;
  chunk_count: number;
  page_count: number;
  skipped: boolean;
  message: string;
}

export interface CorpusChunk {
  chunk_key: string;
  section_label?: string | null;
  parent_heading?: string | null;
  ordinal: number;
  page: number;
  token_count: number;
  text: string;
}

export interface ChatThoughtItem {
  title: string;
  url?: string | null;
  storage_key?: string | null;
  kind?: string | null;
}

export interface ChatThought {
  id: string;
  kind: "plan" | "search" | "links" | "documents" | "status";
  title?: string;
  detail?: string | null;
  items?: ChatThoughtItem[];
}

export interface ChatTurnOut {
  role: "user" | "assistant";
  text: string;
  created_at: string | null;
  turn_id?: number | null;
  sources?: ChatSource[];
  thoughts?: ChatThought[];
  feedback?: "up" | "down" | null;
  feedback_comment?: string | null;
  mode?: "review" | "research" | "draft" | null;
}

export interface ChatAttachment {
  attachment_id: string;
  filename: string;
  char_count: number;
}

export interface LegalBotQuery {
  id: number;
  user_id: number;
  question: string;
  ai_answer: string | null;
  citations: Array<Record<string, unknown>> | null;
  confidence: number;
  tier: number;
  status: string;
  legal_override: string | null;
  overridden_by_id: number | null;
  model_version: string | null;
  context_type?: string | null;
  context_tracker_id?: number | null;
  context_version_id?: number | null;
  context_gmail_thread_id?: string | null;
  created_at: string;
  resolved_at: string | null;
  disclaimer: string;
}

export interface ResearchNote {
  id: number;
  query: string;
  summary: string;
  applicable_regulations: Array<Record<string, unknown>>;
  key_provisions: Array<Record<string, unknown>>;
  implications: string;
  recommended_next_steps: string[];
  citations: Array<Record<string, unknown>>;
  confidence: number;
  status: "draft" | "finalized";
  reviewer_notes: string | null;
  model_version: string | null;
  created_by_id: number;
  finalized_by_id: number | null;
  created_at: string;
  finalized_at: string | null;
}

export interface ResearchSummary {
  id: number;
  query: string;
  status: "draft" | "finalized";
  confidence: number;
  created_at: string;
}

export interface GroundTruthCheck {
  term: string;
  passed: boolean;
}

export interface MSARiskBreakdown {
  overall: number;
  from_ai_clauses: number;
  from_ground_truth: number;
  by_severity: { high: number; medium: number; low: number };
  ground_truth_passed: number;
  ground_truth_failed: number;
  ground_truth_checks: GroundTruthCheck[];
}

export interface NegotiationMemoryEntry {
  id: number;
  tracker_id: number;
  kind: string;
  content: string;
  version_id: number | null;
  created_by_id: number | null;
  created_at: string;
}

export interface MSAEmail {
  id: number;
  direction: "in" | "out";
  from_addr: string;
  to_addr: string;
  subject: string;
  body: string;
  attachment_name: string | null;
  sent_at: string;
  sent_by_id: number | null;
}

export interface MSAAISuggestion {
  order_index: number;
  heading: string | null;
  clause_text: string;
  risk_flag: string;
  confidence: number;
  rationale: string;
  ai_suggestion: string | null;
  original_text?: string | null;
  proposed_text?: string | null;
  category?: string;
  decision: "pending" | "accept" | "modify" | "reject";
  reviewer_edit?: string;
  apply_error?: string;
  apply_note?: string;
  playbook_clause_id?: number | null;
  playbook_clause_type?: string | null;
  standard_position_excerpt?: string | null;
  clause_bank_id?: number | null;
  regulatory_ref?: string | null;
  insert_anchor_hint?: string | null;
}

export interface DocumentVersion {
  id: number;
  tracker_id: number;
  version_number: number;
  source: string;
  filename: string | null;
  mime_type: string | null;
  storage_key: string | null;
  parent_version_id: number | null;
  comparison_id: number | null;
  created_by_id: number | null;
  gmail_message_id: string | null;
  created_at: string;
  download_url: string | null;
}

export interface NegotiationChangeItem {
  diff_index: number;
  title: string;
  old_text: string;
  new_text: string;
  severity: string;
  impact: string;
  suggested_action: string;
  /** Nearest section/clause heading, e.g. "§7. Limitation of Liability". */
  clause_ref?: string;
  /** Precise one-line description of what changed, e.g. 'Changed "30 days" → "60 days"'. */
  change_summary?: string;
  /** Why the change was flagged / reasoning behind the suggested action. */
  rationale?: string;
}

export interface NegotiationChanges {
  comparison_id: number | null;
  summary_report: string | null;
  executive_summary: string | null;
  diff_blocks: DiffBlock[];
  risk_commentary: RiskFlag[];
  llm_narrative: NegotiationChangeItem[];
  from_version_number: number | null;
  to_version_number: number | null;
}

export interface NegotiationTask {
  id: number;
  tracker_id: number;
  version_id: number | null;
  comparison_id: number | null;
  diff_index: number | null;
  title: string;
  description: string;
  suggested_action: string | null;
  severity: string;
  status: string;
  assigned_to_id: number | null;
  due_date: string | null;
  promoted_task_id: number | null;
  resolved_at: string | null;
  created_at: string;
}

export interface ContractTemplate {
  id: number;
  contract_type: string;
  name: string;
  description: string | null;
  template_text: string;
  storage_key: string | null;
  version: number;
  is_active: boolean;
  created_by_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ContractTemplateSummary {
  id: number;
  contract_type: string;
  name: string;
  description: string | null;
  version: number;
  is_active: boolean;
}

export interface TemplateLibraryItem {
  name: string;
  filename: string;
  doc_kind: string;
  contract_type: string;
  description: string | null;
  storage_key: string;
  content_type: string | null;
  size_bytes: number | null;
  updated_at: string | null;
  source: string;
  db_id: number | null;
}

export interface TemplateLibraryCategories {
  doc_kinds: { id: string; label: string }[];
  contract_types: string[];
  allowed_extensions: string[];
  bucket: string;
  prefix: string;
  templates_prefix?: string;
  contracts_prefix?: string;
}

export interface TemplateLibraryPreview {
  name: string;
  filename: string;
  doc_kind: string;
  contract_type: string;
  storage_key: string;
  content_type: string | null;
  size_bytes: number | null;
  text: string;
  char_count: number;
  truncated: boolean;
}

export interface GmailStatus {
  configured: boolean;
  enabled: boolean;
  connected: boolean;
  email: string | null;
}

export interface GmailSettings {
  poll_enabled: boolean;
  poll_labels: string[];
  auto_task_ingest: boolean;
  poll_lookback_days: number;
  watched_threads: { thread_id: string; subject?: string; from_addr?: string; added_at?: string }[];
  watched_senders: string[];
  msa_watched_threads: { thread_id: string; tracker_id?: number | null; subject?: string; vendor_email?: string; added_at?: string }[];
  default_context_module: string;
  last_poll_at: string | null;
  connected: boolean;
  email: string | null;
}

export interface GmailMessageList {
  messages: GmailMessageSummary[];
  next_page_token: string | null;
}

export interface GmailPollSummary {
  tasks_created: number;
  messages_scanned: number;
  skipped: number;
  msa_processed: number;
  msa_ingested?: { message_id: string; tracker_id: number; version_id?: number; filename: string }[];
  msa_auto_created?: { message_id: string; tracker_id: number; thread_id: string; filename: string }[];
  msa_skipped?: number;
  reminders_created?: number;
  sources?: string[];
  hint?: string | null;
  errors: string[];
}

export interface MSAGmailWatch {
  thread_id: string;
  tracker_id?: number | null;
  subject?: string | null;
  vendor_email?: string | null;
  added_at?: string | null;
}

export interface GmailLabel {
  id: string;
  name: string;
  type: string;
}

export interface GmailMessageSummary {
  id: string;
  thread_id: string;
  subject: string;
  from_addr: string;
  to_addr: string;
  snippet: string;
  date: string | null;
}

export interface GmailMessage {
  id: string;
  thread_id: string;
  subject: string;
  from_addr: string;
  to_addr: string;
  body: string;
  date: string | null;
}

export interface GmailThread {
  id: string;
  messages: GmailMessage[];
}

export interface EmailDraft {
  id: number;
  user_id: number;
  task_id: number | null;
  auto_generated: boolean;
  gmail_thread_id: string;
  gmail_message_id: string;
  original_subject: string;
  original_body: string;
  from_addr: string;
  to_addr: string | null;
  draft_subject: string;
  draft_body: string;
  status: string;
  user_feedback: string | null;
  remind_at: string | null;
  model_version: string | null;
  sent_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MSAShare {
  id: number;
  tracker_id: number;
  user_id: number;
  shared_by_id: number;
  access_level: "view" | "edit";
  shared_at: string;
  user_email: string | null;
  user_full_name: string | null;
}

export interface ShareableUser {
  id: number;
  email: string;
  full_name: string;
  role: string;
}

export interface MSATracker {
  id: number;
  vendor_name: string;
  vendor_email: string;
  contract_type: string;
  deal_reference: string | null;
  status: string;
  risk_score: number | null;
  current_version: number;
  redlined_text: string | null;
  ai_suggestions: MSAAISuggestion[] | null;
  template_id: number | null;
  canonical_version_id: number | null;
  executed_version_id: number | null;
  gmail_thread_id: string | null;
  gmail_auto_ingest?: boolean;
  assigned_to_id: number | null;
  review_guidelines?: string | null;
  change_history?: ReviewChangeEntry[] | null;
  risk_breakdown?: MSARiskBreakdown | null;
  created_at: string;
  updated_at: string;
  emails: MSAEmail[];
  my_access_level?: "owner" | "view" | "edit" | null;
  shares?: MSAShare[];
}

export interface MSASummary {
  id: number;
  vendor_name: string;
  contract_type: string;
  status: string;
  risk_score: number | null;
  updated_at: string;
  my_access_level?: "owner" | "view" | "edit" | null;
}

export interface MSADocxOperation {
  op_type: string;
  anchor_id: string | null;
  after_anchor_id: string | null;
  target_text: string | null;
  content: string | null;
  description: string;
  confidence: number;
}

export interface MSADocxOperationResult {
  op_index: number;
  op_type: string;
  description: string;
  status: string;
  message: string;
}

export interface MSAPromptEditPreview {
  revision_id: number | null;
  base_version_id: number;
  base_version_number: number;
  base_text: string;
  edited_text: string;
  change_summary: string | null;
  changes: EditChange[];
  operations: MSADocxOperation[];
  operation_results: MSADocxOperationResult[];
  edit_mode: string;
  structure_hash: string | null;
  diff_blocks: DiffBlock[];
  model_version: string | null;
  ai_fallback?: boolean;
}

export interface MSAPromptRevisionSummary {
  id: number;
  tracker_id: number;
  base_version_id: number;
  instruction: string;
  change_summary: string | null;
  edit_mode: string;
  status: string;
  model_version: string | null;
  created_at: string;
  applied_at: string | null;
}

export interface MSAPromptRevision {
  id: number;
  tracker_id: number;
  base_version_id: number;
  instruction: string;
  selection: string | null;
  base_text: string;
  edited_text: string;
  change_summary: string | null;
  operations: MSADocxOperation[];
  operation_results: MSADocxOperationResult[];
  structure_hash: string | null;
  edit_mode: string;
  diff_blocks: DiffBlock[];
  status: string;
  model_version: string | null;
  resulting_version_id: number | null;
  created_at: string;
}

export interface OnlyOfficeConfig {
  document_server_url: string;
  token: string;
  config: Record<string, unknown>;
  enabled: boolean;
}

export interface MSASuggestionsPreview {
  base_version_id: number;
  base_version_number: number;
  base_text: string;
  edited_text: string;
  diff_blocks: DiffBlock[];
  applied_count: number;
  blocked_count: number;
  accepted_count: number;
  applied: MSAAISuggestion[];
  blocked: MSAAISuggestion[];
}

export interface RegulatoryUpdate {
  id: number;
  source: string;
  source_id: number | null;
  category: string | null;
  title: string;
  summary: string;
  full_text: string | null;
  url: string | null;
  tags: string[];
  relevance_score: number;
  status: "action_required" | "for_information" | "not_relevant";
  published_at: string;
  ingested_at: string;
  triaged_by_id: number | null;
  impact_note: string | null;
}

export interface TrackedSource {
  id: number;
  name: string;
  url: string;
  regulator: string;
  category: string;
  source_type: "web" | "rss";
  enabled: boolean;
  last_fetched_at: string | null;
  last_status: string | null;
  created_at: string;
}

export interface NewsOverview {
  total: number;
  action_required: number;
  new_this_week: number;
  sources_count: number;
  last_refreshed: string | null;
}

export interface DiscoverResult {
  title: string;
  url: string;
  snippet: string;
}

export interface RefreshSummary {
  total_new: number;
  action_required: number;
  sources: { source: string; regulator?: string; new_count: number; errors: string[] }[];
}

export type TaskPriority = "P0" | "P1" | "P2" | "P3";
export type TaskStatus = "todo" | "in_progress" | "done" | "snoozed";

export interface Task {
  id: number;
  title: string;
  description: string | null;
  source: "email" | "manual" | "module";
  source_module: string | null;
  source_ref_id: number | null;
  email_sender: string | null;
  email_subject: string | null;
  email_body: string | null;
  gmail_message_id: string | null;
  gmail_thread_id: string | null;
  priority: TaskPriority;
  priority_score: number;
  status: TaskStatus;
  due_date: string | null;
  estimated_minutes: number | null;
  snoozed_until: string | null;
  created_by_id: number;
  assigned_to_id: number | null;
  tags: string[];
  ai_confidence: number | null;
  ai_rationale: string | null;
  model_version: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface TaskAggregated {
  key: string;
  title: string;
  description: string;
  source_module: string;
  source_ref_id: number;
  priority: TaskPriority;
  priority_score: number;
  due_date: string | null;
  tags: string[];
}

export interface DailyBrief {
  summary: string;
  counts: Record<TaskPriority, number>;
  streak_days: number;
  completed_today: number;
  overdue: number;
  new_gmail_tasks_count: number;
  pending_email_drafts: number;
  top_priorities: Task[];
  aggregated_suggestions: TaskAggregated[];
}

export type FeatureRequestStatus =
  | "submitted"
  | "analysing"
  | "planning"
  | "in_progress"
  | "pr_open"
  | "in_review"
  | "merged"
  | "deploying"
  | "deployed"
  | "failed"
  | "rejected";

export interface AgentLogEntry {
  at: string;
  level: "info" | "warn" | "error" | "success";
  stage: string;
  message: string;
}

export interface FeatureRequest {
  id: number;
  title: string;
  description: string;
  request_type: "bug" | "feature" | "enhancement" | "refactor";
  priority: TaskPriority;
  priority_score: number;
  status: FeatureRequestStatus;
  repository: string | null;
  github_issue_number: number | null;
  github_issue_url: string | null;
  branch_name: string | null;
  pr_number: number | null;
  pr_url: string | null;
  deployment_url: string | null;
  plan: Array<{ step: string; files: string[] }> | null;
  files_touched: string[] | null;
  loc_estimate: number | null;
  diff_summary: string | null;
  agent_log: AgentLogEntry[];
  model_version: string | null;
  created_by_id: number;
  approved_by_id: number | null;
  created_at: string;
  updated_at: string;
  state_changed_at: string;
  pr_opened_at: string | null;
  merged_at: string | null;
  deployed_at: string | null;
}

export interface FeatureRequestSummary {
  id: number;
  title: string;
  request_type: string;
  priority: TaskPriority;
  status: FeatureRequestStatus;
  created_at: string;
  updated_at: string;
}

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  role: string;
  action_type: string;
  module: string;
  input_summary: string | null;
  ai_output_summary: string | null;
  confidence_score: number | null;
  human_decision: string | null;
  model_version: string | null;
  ip_address: string | null;
  session_id: string | null;
  target_id: number | null;
  extra: Record<string, unknown> | null;
  timestamp: string;
}

export interface MetricsSummary {
  total_users: number;
  active_users: number;
  total_documents: number;
  total_queries: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  ai_actions: number;
}

export interface DailyCount {
  day: string;
  count: number;
}

export interface DailyTokenTrend {
  day: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface ModuleDailyTrend {
  day: string;
  module: string;
  count: number;
}

export interface UserSegment {
  segment: string;
  label: string;
  query_range: string;
  count: number;
  percentage: number;
}

export interface ModuleUsage {
  module: string;
  label: string;
  count: number;
}

export interface MetricsUserRow {
  user_id: number;
  email: string;
  full_name: string;
  role: string;
  documents: number;
  queries: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  last_login_at: string | null;
}

export interface MetricsUsersPage {
  items: MetricsUserRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface MetricsDateRange {
  start_date?: string;
  end_date?: string;
}
