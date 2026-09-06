import type {
  RoleId,
  Brief,
  BriefForm,
  BriefSize,
  BriefSummary,
  BriefEvent,
  BriefInboxItem,
  BannerImage,
  BannerImageMessage,
  BriefReferenceImage,
  AgentPrompt,
  BannerTemplateDetail,
  BannerTemplateSummary,
  DesignPrompt,
  ImagePrompt,
  Creative,
  CreativeEdit,
  CreativeVersion,
  DesignQueueItem,
  FigmaExportResult,
  FigmaStatus,
  GenerationQueueItem,
  NotificationFeed,
  AdminOverview,
  AdminBriefRow,
  AdminUser,
  CostingDetail,
  OverviewFilters,
  ReassignSlot,
  RoleDefault,
} from './types';

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

// The session lives in an httpOnly cookie set server-side — deliberately
// invisible to JavaScript. `credentials: "include"` makes the browser store
// the cookie and send it back on every request.
const CREDENTIALS: RequestCredentials = 'include';

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  /** The currently-active role. */
  role: RoleId;
  is_active: boolean;
  /** Roles this identity may act as (for the role switcher). */
  roles: RoleId[];
  active_role: RoleId | null;
}

export interface LoginResult {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface AuthConfig {
  environment: string;
  password_login: boolean;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function handleUnauthorized(status: number) {
  if (status === 401) {
    window.dispatchEvent(new Event('app:unauthorized'));
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: CREDENTIALS,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  });

  if (!res.ok) {
    handleUnauthorized(res.status);
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/** POST multipart form data. Bypasses `request()` because the browser has to set
 *  its own Content-Type (it carries the multipart boundary). */
async function postForm<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    credentials: CREDENTIALS,
    body,
  });
  if (!res.ok) {
    handleUnauthorized(res.status);
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** Drop empty/undefined values and build a `?a=b&…` query string. */
function qs(params: object): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params) as [string, unknown][]) {
    if (v !== undefined && v !== null && v !== '') sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const api = {
  me: () => request<AuthUser>('/api/auth/me'),
  authConfig: () => request<AuthConfig>('/api/auth/config'),
  login: (email: string, password: string) =>
    request<LoginResult>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  switchRole: (role: RoleId) =>
    request<AuthUser>('/api/auth/switch-role', {
      method: 'POST',
      body: JSON.stringify({ role }),
    }),
  listUsers: () => request<AuthUser[]>('/api/users'),

  adminOverview: (filters: OverviewFilters = {}) =>
    request<AdminOverview>(`/api/admin/overview${qs(filters)}`),
  adminBriefs: (
    filters: OverviewFilters & { stage?: string; exported?: boolean; sort?: string } = {},
  ) => request<AdminBriefRow[]>(`/api/admin/briefs${qs(filters)}`),
  adminCosting: () => request<CostingDetail>('/api/admin/costing'),

  adminListUsers: () => request<AdminUser[]>('/api/admin/users'),
  adminCreateUser: (body: {
    email: string;
    full_name: string;
    role?: RoleId;
    password?: string;
    is_active?: boolean;
  }) => request<AdminUser>('/api/admin/users', { method: 'POST', body: JSON.stringify(body) }),
  adminUpdateUser: (
    id: string,
    body: Partial<{ email: string; full_name: string; role: RoleId; is_active: boolean }>,
  ) => request<AdminUser>(`/api/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  adminResetPassword: (id: string, password: string) =>
    request<void>(`/api/admin/users/${id}/password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  adminDeleteUser: (id: string) =>
    request<AdminUser>(`/api/admin/users/${id}`, { method: 'DELETE' }),

  // Admin — default-assignee levers: the account new work auto-routes to per role.
  adminRoleDefaults: () => request<RoleDefault[]>('/api/admin/role-defaults'),
  adminSetRoleDefault: (role: RoleId, user_id: string) =>
    request<RoleDefault>(`/api/admin/role-defaults/${role}`, {
      method: 'PUT',
      body: JSON.stringify({ user_id }),
    }),

  // Notifications — a per-user feed derived from brief events, plus mark-all-read.
  notifications: () => request<NotificationFeed>('/api/notifications'),
  markNotificationsSeen: () => request<void>('/api/notifications/seen', { method: 'POST' }),

  // Briefs
  listBriefs: (q?: string) =>
    request<BriefSummary[]>(`/api/briefs${q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`),
  allBriefs: (q?: string) =>
    request<BriefSummary[]>(`/api/briefs/all${q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`),
  briefInbox: () => request<BriefInboxItem[]>('/api/briefs/inbox'),
  briefAudit: () => request<BriefEvent[]>('/api/briefs/audit'),
  // One brief's full activity timeline (chronological) — the transparency feed.
  briefEvents: (id: string) => request<BriefEvent[]>(`/api/briefs/${id}/events`),
  getBrief: (id: string) => request<Brief>(`/api/briefs/${id}`),
  createBrief: (brief_type: BriefSize, content: BriefForm) =>
    request<Brief>('/api/briefs', {
      method: 'POST',
      body: JSON.stringify({ brief_type, ...content }),
    }),
  updateBrief: (id: string, content: BriefForm) =>
    request<Brief>(`/api/briefs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ ...content }),
    }),
  submitBrief: (id: string) =>
    request<Brief>(`/api/briefs/${id}/submit`, { method: 'POST' }),

  // Reference images — the sample copies / examples the Product Lead attaches to a
  // brief. Uploadable by whoever may edit the brief (author while draft/returned,
  // or the reviewing Marketing Lead); everyone in the chain can view them, and the
  // Designer's hero-image generation uses them as visual references.
  briefReferenceImages: (id: string) =>
    request<BriefReferenceImage[]>(`/api/briefs/${id}/reference-images`),
  uploadBriefReferenceImage: (
    id: string,
    file: File,
    caption?: string,
  ): Promise<BriefReferenceImage> => {
    const body = new FormData();
    body.append('file', file);
    if (caption && caption.trim()) body.append('caption', caption.trim());
    return postForm<BriefReferenceImage>(`/api/briefs/${id}/reference-images`, body);
  },
  deleteBriefReferenceImage: (id: string, imageId: string) =>
    request<void>(`/api/briefs/${id}/reference-images/${imageId}`, { method: 'DELETE' }),
  // The PNG bytes for one reference image: fetch as a blob (cookie travels via
  // credentials) and hand back an object URL for an <img>. Callers revoke it.
  briefReferenceImageObjectUrl: async (id: string, imageId: string): Promise<string> => {
    const res = await fetch(`${BASE}/api/briefs/${id}/reference-images/${imageId}/content`, {
      credentials: CREDENTIALS,
    });
    if (!res.ok) throw new ApiError(res.status, 'Could not load image');
    return URL.createObjectURL(await res.blob());
  },

  // Reassign the brief's current-stage task to another active same-role teammate.
  // `slot` is optional — the backend derives it from the caller's role + stage.
  reassignBrief: (id: string, assignee_id: string, slot?: ReassignSlot, note?: string) =>
    request<Brief>(`/api/briefs/${id}/reassign`, {
      method: 'POST',
      body: JSON.stringify({ assignee_id, slot: slot ?? null, note: note?.trim() || null }),
    }),

  // Approval sign-off (Strategist + Marketing + Product, all required)
  approvalQueue: () => request<BriefSummary[]>('/api/briefs/approval-queue'),
  approvalSignoff: (id: string, action: 'approve' | 'request_changes', note?: string) =>
    request<Brief>(`/api/briefs/${id}/approval`, {
      method: 'POST',
      body: JSON.stringify({ action, note }),
    }),

  // Send the brief back a step for changes (Copywriter → author, Designer →
  // Copywriter). The target stage is derived server-side from where the brief is;
  // the note (reason) is required.
  rejectBrief: (id: string, note: string) =>
    request<Brief>(`/api/briefs/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),

  // This brief's own copy direction — the individual-level copy prompt, written by
  // the author / a Product Lead. Blank clears it, leaving the master Prompt Studio
  // prompts to run alone.
  setCopyPrompt: (id: string, prompt: string) =>
    request<Brief>(`/api/briefs/${id}/copy-prompt`, {
      method: 'PUT',
      body: JSON.stringify({ prompt }),
    }),

  // Copies — brief → copy generation (Copy Agent), owned by the Copywriter
  copywritingQueue: () => request<GenerationQueueItem[]>('/api/briefs/copywriting-queue'),
  listCreatives: (id: string) => request<Creative[]>(`/api/briefs/${id}/creatives`),
  generateCreatives: (id: string, count = 6) =>
    request<Creative[]>(`/api/briefs/${id}/creatives`, {
      method: 'POST',
      body: JSON.stringify({ count }),
    }),
  // Save the Copywriter's edits and submit the brief for approval (stage →
  // approval). Approvers + Designer auto-route to the admin-configured defaults.
  submitCopies: (id: string, creatives: CreativeEdit[]) =>
    request<Brief>(`/api/briefs/${id}/creatives/handoff`, {
      method: 'POST',
      body: JSON.stringify({ creatives }),
    }),
  // Per-creative version history — list, edit (creates a new live version), and
  // select a prior version as live. Copywriter-only while the brief is in copywriting.
  creativeVersions: (id: string, creativeId: string) =>
    request<CreativeVersion[]>(`/api/briefs/${id}/creatives/${creativeId}/versions`),
  editCreative: (id: string, creativeId: string, edit: CreativeEdit) =>
    request<Creative>(`/api/briefs/${id}/creatives/${creativeId}`, {
      method: 'PATCH',
      body: JSON.stringify({
        headline: edit.headline,
        body: edit.body,
        cta: edit.cta,
        visual_reference: edit.visual_reference,
        entity_attribution: edit.entity_attribution,
        terms: edit.terms,
      }),
    }),
  selectCreativeVersion: (id: string, creativeId: string, versionId: string) =>
    request<Creative>(`/api/briefs/${id}/creatives/${creativeId}/versions/${versionId}/select`, {
      method: 'POST',
    }),

  // The Designer's queue — approved briefs handed off, each with banner-production progress.
  designQueue: () => request<DesignQueueItem[]>('/api/briefs/design-queue'),

  // Banners — the Designer's flow: Nano Banana hero images → review → Figma export.
  bannerImages: (id: string) => request<BannerImage[]>(`/api/briefs/${id}/banner-images`),
  // template_id art-directs the hero photos for that template's layout (e.g.
  // messaging: subject left, copy right).
  generateBannerImages: (id: string, template_id?: string) =>
    request<BannerImage[]>(`/api/briefs/${id}/banner-images`, {
      method: 'POST',
      body: JSON.stringify({ template_id }),
    }),
  regenerateBannerImage: (id: string, imageId: string, template_id?: string) =>
    request<BannerImage>(`/api/briefs/${id}/banner-images/${imageId}/regenerate`, {
      method: 'POST',
      body: JSON.stringify({ template_id }),
    }),
  approveBannerImages: (id: string) =>
    request<BannerImage[]>(`/api/briefs/${id}/banner-images/approve`, { method: 'POST' }),
  // Swap in a Designer-supplied photo when the AI output isn't right.
  uploadBannerImage: (id: string, imageId: string, file: File): Promise<BannerImage> => {
    const body = new FormData();
    body.append('file', file);
    return postForm<BannerImage>(`/api/briefs/${id}/banner-images/${imageId}/upload`, body);
  },
  // Design Studio manual edit — the crop/straighten/tune work happens on a canvas
  // in the browser (see lib/imageEdit); this posts the flattened result, which the
  // server appends to the image's version thread just like an AI edit. `summary`
  // is the human-readable list of what changed, shown in the version history.
  manualEditBannerImage: (
    id: string,
    imageId: string,
    file: File,
    summary: string,
  ): Promise<{ image: BannerImage; message: BannerImageMessage }> => {
    const body = new FormData();
    body.append('file', file);
    body.append('summary', summary);
    return postForm(`/api/briefs/${id}/banner-images/${imageId}/manual-edit`, body);
  },
  // Send the Figma-exported design to the Marketing Lead for creative review —
  // the Designer's explicit final action, once they've reviewed the exported file.
  submitDesignForReview: (id: string) =>
    request<Brief>(`/api/briefs/${id}/design/submit-for-review`, { method: 'POST' }),
  // Chat-with-image: the thread of comments + versions for one hero image, and
  // posting a comment that edits the image (returns the refreshed image + the turn).
  bannerImageMessages: (id: string, imageId: string) =>
    request<BannerImageMessage[]>(`/api/briefs/${id}/banner-images/${imageId}/messages`),
  // Multipart, not JSON: the Designer can attach reference images to the turn
  // ("make it look like this"). They steer this one edit and aren't stored.
  commentBannerImage: (
    id: string,
    imageId: string,
    comment: string,
    fromMessageId?: string,
    references: File[] = [],
  ) => {
    const body = new FormData();
    body.append('comment', comment);
    // Only when set — FastAPI parses the field as a UUID, and an empty string is a
    // 422 rather than "no version given".
    if (fromMessageId) body.append('from_message_id', fromMessageId);
    for (const file of references) body.append('references', file);
    return postForm<{ image: BannerImage; message: BannerImageMessage }>(
      `/api/briefs/${id}/banner-images/${imageId}/comment`,
      body,
    );
  },
  // Make a thread version the live one (what the card + Figma export use).
  selectBannerImageVersion: (id: string, imageId: string, messageId: string) =>
    request<BannerImage>(
      `/api/briefs/${id}/banner-images/${imageId}/messages/${messageId}/select`,
      { method: 'POST' },
    ),
  figmaExport: (id: string, file_name: string, sizes?: string[], template_id?: string) =>
    request<FigmaExportResult>(`/api/briefs/${id}/figma-export`, {
      method: 'POST',
      body: JSON.stringify({ file_name, sizes, template_id }),
    }),
  // The banner-template gallery — the Designer picks which one to generate the
  // hero images for and render with. `category` narrows it to the family the
  // Product Lead locked on the brief.
  bannerTemplates: (category?: string) =>
    request<BannerTemplateSummary[]>(
      `/api/banner-templates${category ? `?category=${encodeURIComponent(category)}` : ''}`,
    ),
  bannerTemplate: (templateId: string) =>
    request<BannerTemplateDetail>(`/api/banner-templates/${templateId}`),
  // The template's reference artwork (the sample banner the Designer picks by).
  // Fetched as a blob; the session cookie travels via credentials: "include".
  bannerTemplatePreviewObjectUrl: async (templateId: string): Promise<string> => {
    const res = await fetch(`${BASE}/api/banner-templates/${templateId}/preview`, {
      credentials: CREDENTIALS,
    });
    if (!res.ok) throw new ApiError(res.status, 'Could not load template preview');
    return URL.createObjectURL(await res.blob());
  },
  // Admin: attach / drop a template's reference artwork.
  uploadBannerTemplatePreview: (templateId: string, file: File): Promise<BannerTemplateSummary> => {
    const body = new FormData();
    body.append('file', file);
    return postForm<BannerTemplateSummary>(`/api/banner-templates/${templateId}/preview`, body);
  },
  deleteBannerTemplatePreview: (templateId: string) =>
    request<BannerTemplateSummary>(`/api/banner-templates/${templateId}/preview`, {
      method: 'DELETE',
    }),
  // The Designer's template pick for a brief — recorded before the hero images are
  // generated, then reused by regeneration and the Figma export.
  selectBannerTemplate: (id: string, template_id: string) =>
    request<Brief>(`/api/briefs/${id}/banner-template`, {
      method: 'PUT',
      body: JSON.stringify({ template_id }),
    }),
  // The default banner template — its sizes power the pre-export size picker.
  defaultBannerTemplate: () =>
    request<BannerTemplateDetail>('/api/banner-templates/default'),
  // Prompt Studio — the current user's hero-image art-direction per template.
  imagePrompts: () => request<ImagePrompt[]>('/api/image-prompts'),
  // The shared design-prompt base every hero image uses (editable per-user).
  designPrompt: () => request<DesignPrompt>('/api/image-prompts/base'),
  setDesignPrompt: (prompt: string, enabled: boolean) =>
    request<DesignPrompt>('/api/image-prompts/base', {
      method: 'PUT',
      body: JSON.stringify({ prompt, enabled }),
    }),
  resetDesignPrompt: () =>
    request<DesignPrompt>('/api/image-prompts/base', { method: 'DELETE' }),
  setImagePrompt: (templateId: string, prompt: string, enabled: boolean) =>
    request<ImagePrompt>(`/api/image-prompts/${templateId}`, {
      method: 'PUT',
      body: JSON.stringify({ prompt, enabled }),
    }),
  resetImagePrompt: (templateId: string) =>
    request<ImagePrompt>(`/api/image-prompts/${templateId}`, { method: 'DELETE' }),
  // Prompt Studio — the current user's instruction append per pipeline agent.
  agentPrompts: () => request<AgentPrompt[]>('/api/agent-prompts'),
  setAgentPrompt: (kind: string, prompt: string, enabled: boolean) =>
    request<AgentPrompt>(`/api/agent-prompts/${kind}`, {
      method: 'PUT',
      body: JSON.stringify({ prompt, enabled }),
    }),
  resetAgentPrompt: (kind: string) =>
    request<AgentPrompt>(`/api/agent-prompts/${kind}`, { method: 'DELETE' }),
  // Figma connection (in-app OAuth). status reports whether the backend can reach
  // Figma; connect returns a URL to open in a new tab to authorize.
  figmaStatus: () => request<FigmaStatus>('/api/figma/status'),
  figmaConnect: () => request<{ authorize_url: string }>('/api/figma/connect', { method: 'POST' }),
  figmaDisconnect: () => request<{ disconnected: boolean }>('/api/figma/connect', { method: 'DELETE' }),
  // The image bytes: fetch as a blob (cookie travels via credentials) and hand
  // back an object URL for an <img> tag. Callers revoke the URL when done.
  bannerImageObjectUrl: async (id: string, imageId: string): Promise<string> => {
    const res = await fetch(`${BASE}/api/briefs/${id}/banner-images/${imageId}/content`, {
      credentials: CREDENTIALS,
    });
    if (!res.ok) throw new ApiError(res.status, 'Could not load image');
    return URL.createObjectURL(await res.blob());
  },
  // The PNG bytes for one version in a chat thread (scroll-back history).
  bannerImageMessageObjectUrl: async (
    id: string,
    imageId: string,
    messageId: string,
  ): Promise<string> => {
    const res = await fetch(
      `${BASE}/api/briefs/${id}/banner-images/${imageId}/messages/${messageId}/content`,
      { credentials: CREDENTIALS },
    );
    if (!res.ok) throw new ApiError(res.status, 'Could not load image');
    return URL.createObjectURL(await res.blob());
  },
  deleteBrief: (id: string) => request<void>(`/api/briefs/${id}`, { method: 'DELETE' }),
  extractBrief: (brief_type: BriefSize, raw_text: string) =>
    request<{ values: BriefForm; model_version: string }>('/api/briefs/extract', {
      method: 'POST',
      body: JSON.stringify({ brief_type, raw_text }),
    }),
};

export { ApiError };
