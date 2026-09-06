// Domain model for the campaign orchestration platform.
// The whole system is a *sequential state machine*: a brief is created, then
// handed role-to-role down a linear chain. Each person mostly waits for work
// to arrive — so "where is this in the chain" and "is it on me right now" are
// the two facts the UI exists to surface.

export type RoleId = 'CW' | 'ML' | 'PL' | 'DS' | 'AD';

export interface Role {
  id: RoleId;
  title: string;
  short: string;
  blurb: string;
  /** Capability keys this role holds — the RBAC matrix, turned into code. */
  can: Capability[];
  /** Nav entries for this role's app shell. */
  nav: NavItem[];
  /** Landing route. */
  home: string;
  accent: string; // hue used for the role avatar ring only
}

export type Capability =
  | 'brief.create'
  | 'brief.viewOwn'
  | 'brief.viewTeam'
  | 'brief.viewAll'
  | 'copy.write'
  | 'approve.briefReview'
  | 'approve.creativeReview'
  | 'approve.finalSignoff'
  | 'killswitch'
  | 'design.execute'
  | 'admin.view'
  | 'admin.users'
  | 'audit.view';

export interface NavItem {
  label: string;
  to: string;
  icon: string; // lucide icon name
  badgeKey?: BadgeKey; // live count driver
}

export type BadgeKey =
  | 'pl.mybriefs'
  | 'cw.copies'
  | 'ml.approvals'
  | 'pl.approvals'
  | 'ds.assets'
  | 'inbox';

// ----- The state machine -------------------------------------------------

export type Stage =
  | 'draft'
  | 'brief_review'
  | 'copywriting'
  | 'design'
  | 'creative_review'
  | 'final_signoff'
  | 'completed'
  // Terminal/legacy alias still surfaced by the table status cells.
  | 'approval';

export interface StageMeta {
  id: Stage;
  label: string;
  owner: RoleId | 'AUTO' | 'SYSTEM';
  hueVar: string; // CSS var name for the stage hue
  /** Short description of what happens here. */
  detail: string;
}

export type BriefType = 'Performance' | 'Brand' | 'In-App' | 'Influencer' | 'Reactive';

// ----- Intake briefs (DB-backed) -----------------------------------------
// Small & Medium share one template (sm_* fields); Large uses lg_* fields.

export type BriefSize = 'small' | 'medium' | 'large';
export type BriefStatus = 'draft' | 'submitted' | 'approved' | 'changes_requested';

/** Position in the linear pipeline. Mirrors the backend BriefStage. */
export type BriefStage =
  | 'draft'
  | 'brief_review'
  | 'copywriting'
  | 'design'
  | 'creative_review'
  | 'final_signoff'
  | 'completed';

/** A single approval checkpoint's state. Mirrors the backend Gate1State. */
export type Gate1LaneState = 'pending' | 'approved' | 'changes_requested';

/** A reassignable assignee slot. Mirrors the backend ReassignSlot. The current
 *  holder of a slot can hand it to another active user of the same role. */
export type ReassignSlot =
  | 'author'
  | 'marketing_brief'
  | 'copywriter'
  | 'designer'
  | 'marketing_creative'
  | 'product';

/** Every editable content field. Mirrors the backend BriefContent schema. */
export type BriefFieldKey =
  | 'banner_category'
  | 'project_name' | 'product_name' | 'owner_name' | 'brief_date' | 'expected_date'
  | 'sm_go_live_timeline' | 'sm_one_line_summary' | 'sm_primary_goal' | 'sm_business_kpi'
  | 'sm_strategic_context' | 'sm_audience_who' | 'sm_audience_segment' | 'sm_audience_exclusions'
  | 'sm_mandatories_tnc' | 'sm_platforms' | 'sm_dimensions_specs' | 'sm_final_ui_screen'
  | 'sm_samples_references'
  | 'lg_project_purpose' | 'lg_business_objective' | 'lg_marketing_objective'
  | 'lg_communication_objective' | 'lg_effectiveness_metric' | 'lg_ideal_customer'
  | 'lg_demo_age' | 'lg_demo_gender' | 'lg_demo_top_cities' | 'lg_goals_motivations'
  | 'lg_category_insight' | 'lg_conservative_target' | 'lg_aspirational_target'
  | 'lg_product_insight' | 'lg_key_markets' | 'lg_competition' | 'lg_product_features'
  | 'lg_key_features_deliverables' | 'lg_unique_offerings'
  | 'lg_think_before' | 'lg_think_after' | 'lg_feel_before' | 'lg_feel_after'
  | 'lg_do_before' | 'lg_do_after'
  | 'lg_cultural_sensitivity' | 'lg_languages' | 'lg_other_considerations' | 'lg_deliverables';

export type BriefForm = Partial<Record<BriefFieldKey, string>>;

export interface Brief extends BriefForm {
  id: string;
  brief_type: BriefSize;
  status: BriefStatus;
  stage: BriefStage;
  creator_id: string;
  // Task allocation — auto-routed to admin-configured role defaults.
  copywriter_id: string | null;
  marketing_id: string | null;
  product_id: string | null;
  designer_id: string | null;
  review_note: string | null;
  reviewer_id: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;

  // Campaign budget (display only)
  budget_inr: number | null;

  // Approval checkpoints (ML on the brief + design, PL final sign-off)
  brief_review_state: Gate1LaneState;
  creative_review_state: Gate1LaneState;
  final_signoff_state: Gate1LaneState;
  brief_review_by_id: string | null;
  creative_review_by_id: string | null;
  final_signoff_by_id: string | null;
  brief_review_at: string | null;
  creative_review_at: string | null;
  final_signoff_at: string | null;

  // The banner template the Designer picked inside the brief's category, before
  // generating hero images — also what the Figma export renders with.
  banner_template_id: string | null;

  // This brief's own copy direction — the individual-level copy prompt, set by the
  // author / a Product Lead. Layers on top of their master Prompt Studio prompt.
  copy_prompt: string | null;

  // Figma export (Designer)
  figma_file_key: string | null;
  figma_file_url: string | null;
  figma_exported_at: string | null;

  // Sample/example images attached to the brief (metadata only — the PNG bytes are
  // fetched separately from the content endpoint).
  reference_images: BriefReferenceImage[];
}

/** One sample/example image attached to a brief. Mirrors backend
 *  BriefReferenceImageOut (bytes excluded — fetched from the content endpoint). */
export interface BriefReferenceImage {
  id: string;
  brief_id: string;
  filename: string;
  caption: string | null;
  mime_type: string;
  uploaded_by_id: string | null;
  uploaded_by_name: string;
  created_at: string;
}

/** One creative's AI hero image. Mirrors backend BannerImageOut (bytes excluded —
 *  the PNG is fetched separately from the content endpoint). */
export interface BannerImage {
  id: string;
  creative_id: string;
  brief_id: string;
  status: 'pending' | 'approved';
  model_version: string;
  active_message_id: string | null; // the chat version currently selected as live
  updated_at: string;
}

/** One turn in the Designer's chat with a hero image. Mirrors backend
 *  BannerImageMessageOut (bytes excluded — each version's PNG is fetched from the
 *  message content endpoint). `comment` is null on the base/seed version. */
export interface BannerImageMessage {
  id: string;
  image_id: string;
  comment: string | null;
  model_version: string;
  created_at: string;
}

/** Where an export landed. Mirrors backend FigmaExportResult. */
export interface FigmaExportResult {
  file_key: string;
  file_url: string;
  creatives: number;
  sizes: number;
}

/** One ad size (performance-static format) offered by a banner template. */
export interface BannerSize {
  name: string;
  w: number;
  h: number;
  pos: string;
}

/** A banner template gallery card. Mirrors backend BannerTemplateSummary. */
export interface BannerTemplateSummary {
  id: string;
  name: string;
  category: string;
  description: string;
  is_default: boolean;
  is_builtin: boolean;
  size_names: string[];
  /** True when reference artwork is uploaded — the picker shows the sample banner
   *  (fetched from the preview endpoint) instead of a text-only card. */
  has_preview: boolean;
  updated_at: string;
  created_at: string;
}

/** One aspect the hero photo gets centre-cropped to for a given ad size. `exact`
 *  is false when the layout sizes the hero from the copy block, so the aspect is a
 *  range (min…max) rather than a value. Mirrors render.hero_guides_for. */
export interface HeroCrop {
  name: string;
  aspect: number;
  min: number;
  max: number;
  exact: boolean;
}

/** Where the copy column sits when it's laid *over* the hero (full-bleed
 *  templates only), as fractions of the creative. */
export interface HeroCopyZone {
  side: 'left' | 'right';
  x0: number;
  x1: number;
  footer: number;
}

/** How a template crops the hero — powers the Design Studio's crop guides. */
export interface HeroGuides {
  mode: 'full-bleed' | 'framed';
  crops: HeroCrop[];
  copy: HeroCopyZone | null;
}

/** A banner template's preview details. Mirrors backend BannerTemplateDetail. */
export interface BannerTemplateDetail {
  id: string;
  name: string;
  description: string;
  is_default: boolean;
  is_builtin: boolean;
  size_names: string[];
  sizes: BannerSize[];
  brand: Record<string, unknown>;
  footer_left: string;
  footer_right: string;
  hero_guides: HeroGuides;
  updated_at: string;
  created_at: string;
}

/** One image use-case (a banner template) in the Prompt Studio — the current
 *  user's hero-photo art-direction for it. Mirrors backend ImagePromptOut. */
export interface ImagePrompt {
  template_id: string;
  template_name: string;
  size_names: string[];
  default_prompt: string;
  prompt: string;
  is_custom: boolean;
  enabled: boolean;
  image_aspect: string;
  image_size: string;
  updated_at: string | null;
}

/** One pipeline agent in the Prompt Studio — the current user's prompt append for
 *  it, plus the read-only base prompt. Mirrors backend AgentPromptOut. */
export interface AgentPrompt {
  kind: string;
  name: string;
  role: string;
  description: string;
  stage: string;
  base_prompt: string;
  output_label: string;
  append: string;
  is_custom: boolean;
  enabled: boolean;
  updated_at: string | null;
}

/** The shared hero-image "design prompt" base for the current user. Mirrors
 *  backend DesignPromptOut. */
export interface DesignPrompt {
  default_prompt: string;
  prompt: string;
  is_custom: boolean;
  enabled: boolean;
  updated_at: string | null;
}

/** Figma connection state. Mirrors the backend /api/figma/status payload. */
export interface FigmaStatus {
  connected: boolean;
  handle: string | null;
  reason: string | null;
}

export interface BriefSummary {
  id: string;
  brief_type: BriefSize;
  status: BriefStatus;
  stage: BriefStage;
  project_name: string | null;
  product_name: string | null;
  owner_name: string | null;
  budget_inr: number | null;
  submitted_at: string | null;
  updated_at: string;
}

/** One immutable entry in a brief's audit trail. Mirrors backend BriefEventOut. */
export interface BriefEvent {
  id: string;
  brief_id: string;
  kind:
    | 'created'
    | 'submitted'
    | 'approved'
    | 'changes_requested'
    | 'reference_added'
    | 'reference_removed'
    | 'assigned'
    | 'creatives_generated'
    | 'copies_submitted'
    | 'gate1_signoff'
    | 'gate1_cleared'
    | 'banner_template_selected'
    | 'banner_images_generated'
    | 'banner_image_uploaded'
    | 'banner_image_edited'
    | 'banner_images_approved'
    | 'design_submitted'
    | 'figma_exported';
  action: string;
  actor_id: string | null;
  actor_name: string;
  actor_role: RoleId;
  note: string | null;
  at: string;
  brief_title: string | null;
}

/** One generated ad creative in the standard format. Mirrors backend CreativeOut. */
export interface Creative {
  id: string;
  brief_id: string;
  position: number;
  visual_reference: string | null;
  headline: string;
  body: string;
  cta: string;
  entity_attribution: string | null;
  terms: string | null;
  model_version: string;
  /** Which version's copy is currently live on this creative. */
  active_version_id: string | null;
  created_at: string;
}

/** One entry in a creative's version history. Mirrors backend CreativeVersionOut. */
export interface CreativeVersion {
  id: string;
  creative_id: string;
  label: string; // "Generated" | "Edited"
  visual_reference: string | null;
  headline: string;
  body: string;
  cta: string;
  entity_attribution: string | null;
  terms: string | null;
  editor_name: string | null;
  model_version: string;
  created_at: string;
  is_active: boolean;
}

/** The Strategist's editable fields of one creative, sent on handoff to design. */
export interface CreativeEdit {
  id: string;
  headline: string;
  body: string;
  cta: string;
  visual_reference: string | null;
  entity_attribution: string | null;
  terms: string | null;
}

/** A Gate-1-cleared brief in the Strategist's creative-generation queue. */
export interface GenerationQueueItem {
  id: string;
  brief_type: BriefSize;
  stage: BriefStage;
  project_name: string | null;
  product_name: string | null;
  owner_name: string | null;
  budget_inr: number | null;
  creative_count: number;
  updated_at: string;
}

/** A brief in the Designer's queue, with its banner-production progress.
 *  Mirrors backend DesignQueueItem. */
export interface DesignQueueItem {
  id: string;
  brief_type: BriefSize;
  stage: BriefStage;
  project_name: string | null;
  product_name: string | null;
  owner_name: string | null;
  budget_inr: number | null;
  creative_count: number;
  image_count: number;
  approved_count: number;
  figma_file_url: string | null;
  figma_exported_at: string | null;
  updated_at: string;
}

/** One notification — a brief event surfaced to the signed-in user.
 *  Mirrors backend NotificationOut. */
export interface AppNotification {
  id: string;
  brief_id: string;
  brief_title: string;
  kind: string;
  title: string;
  body: string;
  actor_name: string;
  actor_role: RoleId;
  at: string;
  read: boolean;
}

/** The notification feed + unread count. Mirrors backend NotificationFeed. */
export interface NotificationFeed {
  items: AppNotification[];
  unread_count: number;
}

/** A brief that needs the creator's action now. Mirrors backend BriefInboxItem. */
export interface BriefInboxItem {
  id: string;
  brief_type: BriefSize;
  stage: BriefStage;
  status: BriefStatus;
  title: string;
  cta: string;
  priority: 'high' | 'normal';
  review_note: string | null;
  updated_at: string;
}

export interface Person {
  id: string;
  name: string;
  role: RoleId;
}

/** Full account record for the admin user-management directory. */
export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  /** Primary role for this account. Prefer `roles` when present. */
  role: RoleId;
  is_active: boolean;
  created_at: string;
  /** Roles this account may act as. */
  roles: RoleId[];
}

/** The default account new work auto-routes to for one role. */
export interface RoleDefault {
  role: RoleId;
  role_label: string;
  user_id: string | null;
  full_name: string | null;
}

/** The Admin dashboard rollup. Mirrors backend AdminOverview. */
export interface AdminOverview {
  totals: {
    draft: number;
    brief_review: number;
    copywriting: number;
    design: number;
    creative_review: number;
    final_signoff: number;
    completed: number;
  };
  by_status: { draft: number; submitted: number; approved: number; changes_requested: number };
  pending: {
    brief_review_total: number;
    awaiting_copy: number;
    copywriting_total: number;
    design_total: number;
    creative_review_total: number;
    final_signoff_total: number;
  };
  costing: {
    total_calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_inr: number;
    avg_latency_ms: number;
    by_operation: {
      operation: string;
      calls: number;
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
      avg_latency_ms: number;
      cost_inr: number;
    }[];
  };
  throughput: { exported: number; change_requests: number; avg_lead_time_hours: number | null };
  oldest_pending: { id: string; title: string; stage: BriefStage; waiting_days: number; updated_at: string }[];
  spend_trend: TrendPoint[];
  throughput_trend: TrendPoint[];
  filter_options: { products: string[] };
}

/** One point in a dashboard time-series. Mirrors backend TrendPoint. */
export interface TrendPoint {
  bucket: string; // ISO date (day or week bucket)
  value: number;
}

/** One (day, operation) spend bucket. Mirrors backend OperationTrendPoint. */
export interface OperationTrendPoint {
  bucket: string; // ISO date
  operation: string;
  value: number;
}

/** The dashboard's date-range + entity filters, serialised to query params. */
export interface OverviewFilters {
  start?: string; // ISO date
  end?: string; // ISO date
  status?: BriefStatus;
  product?: string;
  user_id?: string;
}

/** One brief in the filtered oversight list. Mirrors backend AdminBriefRow. */
export interface AdminBriefRow {
  id: string;
  title: string;
  stage: BriefStage;
  status: BriefStatus;
  product: string | null;
  waiting_days: number;
  updated_at: string;
  exported: boolean;
}

/** One traced model call. Mirrors backend AiCallItem. */
export interface AiCallItem {
  id: string;
  operation: string;
  model: string;
  brief_id: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  latency_ms: number;
  cost_inr: number;
  status: string;
  at: string;
}

/** Granular AI-spend breakdown. Mirrors backend CostingDetail. */
export interface CostingDetail {
  windows: { today_inr: number; week_inr: number; total_inr: number };
  totals: {
    calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    cost_inr: number;
    avg_latency_ms: number;
  };
  spend_trend: TrendPoint[];
  spend_by_operation_trend: OperationTrendPoint[];
  by_operation: {
    operation: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    input_cost_inr: number;
    output_cost_inr: number;
    cost_inr: number;
    avg_latency_ms: number;
  }[];
  by_model: { model: string; calls: number; input_tokens: number; output_tokens: number; cost_inr: number }[];
  by_brief: { brief_id: string | null; title: string; calls: number; total_tokens: number; cost_inr: number }[];
  recent_calls: AiCallItem[];
}
