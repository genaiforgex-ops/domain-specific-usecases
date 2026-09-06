import type { Role, RoleId, StageMeta, Stage, Person } from './types';

// The linear handoff chain, in order. The pipeline rail renders straight from
// this array — order here *is* the source of truth for sequence.
export const STAGES: StageMeta[] = [
  { id: 'draft', label: 'Brief', owner: 'PL', hueVar: '--stage-draft', detail: 'Product Lead authors against the enforced template.' },
  { id: 'brief_review', label: 'Brief review', owner: 'ML', hueVar: '--stage-gate', detail: 'Marketing Lead reviews, edits and approves the brief.' },
  { id: 'copywriting', label: 'Copywriting', owner: 'CW', hueVar: '--stage-generate', detail: 'Copywriter drafts and edits the copies.' },
  { id: 'design', label: 'Design', owner: 'DS', hueVar: '--stage-design', detail: 'Designer produces banners in Figma / raster workspace.' },
  { id: 'creative_review', label: 'Creative review', owner: 'ML', hueVar: '--stage-gate', detail: 'Marketing Lead approves the finished design.' },
  { id: 'final_signoff', label: 'Sign-off', owner: 'PL', hueVar: '--stage-gate', detail: 'Product Lead gives the final "good to go".' },
];

export const stageMeta = (s: Stage): StageMeta => STAGES.find((x) => x.id === s)!;
export const stageIndex = (s: Stage): number => STAGES.findIndex((x) => x.id === s);

export const ROLES: Record<RoleId, Role> = {
  CW: {
    id: 'CW',
    title: 'Copywriter',
    short: 'Copywriter',
    blurb: 'Write and edit the copies for approved briefs.',
    accent: '#6e6e74',
    home: '/home',
    can: ['brief.viewAll', 'copy.write'],
    nav: [
      { label: 'Home', to: '/home', icon: 'Home' },
      { label: 'Copies', to: '/copies', icon: 'Sparkles', badgeKey: 'cw.copies' },
      { label: 'Context Studio', to: '/prompts', icon: 'SlidersHorizontal' },
      { label: 'Inbox', to: '/inbox', icon: 'Inbox', badgeKey: 'inbox' },
      { label: 'Search', to: '/search', icon: 'Search' },
    ],
  },
  ML: {
    id: 'ML',
    title: 'Marketing Lead',
    short: 'Mktg Lead',
    blurb: 'Review and approve the brief, then approve the design.',
    accent: '#57575f',
    home: '/home',
    can: ['brief.viewAll', 'approve.briefReview', 'approve.creativeReview', 'killswitch'],
    nav: [
      { label: 'Home', to: '/home', icon: 'Home' },
      { label: 'Approvals', to: '/approvals', icon: 'ShieldCheck', badgeKey: 'ml.approvals' },
      { label: 'Inbox', to: '/inbox', icon: 'Inbox', badgeKey: 'inbox' },
      { label: 'Search', to: '/search', icon: 'Search' },
    ],
  },
  PL: {
    id: 'PL',
    title: 'Product Lead',
    short: 'Product Lead',
    blurb: 'Author briefs, then give the final sign-off.',
    accent: '#3f3f45',
    home: '/home',
    can: ['brief.create', 'brief.viewOwn', 'brief.viewAll', 'approve.finalSignoff'],
    nav: [
      { label: 'Home', to: '/home', icon: 'Home' },
      { label: 'My Briefs', to: '/briefs', icon: 'FileText', badgeKey: 'pl.mybriefs' },
      { label: 'New Brief', to: '/briefs/new', icon: 'Plus' },
      { label: 'Approvals', to: '/approvals', icon: 'ShieldCheck', badgeKey: 'pl.approvals' },
      { label: 'Context Studio', to: '/prompts', icon: 'SlidersHorizontal' },
      { label: 'Inbox', to: '/inbox', icon: 'Inbox', badgeKey: 'inbox' },
      { label: 'Search', to: '/search', icon: 'Search' },
    ],
  },
  DS: {
    id: 'DS',
    title: 'Designer',
    short: 'Designer',
    blurb: 'Generate, review and ship banners for assigned briefs.',
    accent: '#83838a',
    home: '/home',
    can: ['design.execute'],
    nav: [
      { label: 'Home', to: '/home', icon: 'Home' },
      { label: 'My Assets', to: '/assets', icon: 'Palette', badgeKey: 'ds.assets' },
      { label: 'Context Studio', to: '/prompts', icon: 'SlidersHorizontal' },
      { label: 'Inbox', to: '/inbox', icon: 'Inbox', badgeKey: 'inbox' },
      { label: 'Search', to: '/search', icon: 'Search' },
    ],
  },
  AD: {
    id: 'AD',
    title: 'Admin',
    short: 'Admin',
    blurb: 'Cross-pipeline oversight — costing, pending work and throughput.',
    accent: '#2c2c31',
    home: '/dashboard',
    can: ['brief.viewAll', 'admin.view', 'admin.users', 'audit.view'],
    nav: [
      { label: 'Dashboard', to: '/dashboard', icon: 'LayoutDashboard' },
      { label: 'Costing', to: '/costing', icon: 'Receipt' },
      { label: 'Users', to: '/users', icon: 'UserCog' },
      { label: 'Assignees', to: '/assignees', icon: 'Users' },
      { label: 'Search', to: '/search', icon: 'Search' },
    ],
  },
};

export const ROLE_ORDER: RoleId[] = ['CW', 'ML', 'PL', 'DS', 'AD'];

// People directory — one signed-in identity per role for the demo.
export const PEOPLE: Record<RoleId, Person> = {
  CW: { id: 'u-cw', name: 'Priya Nair', role: 'CW' },
  ML: { id: 'u-ml', name: 'Rohan Kapoor', role: 'ML' },
  PL: { id: 'u-pl', name: 'Sana Iqbal', role: 'PL' },
  DS: { id: 'u-ds', name: 'Karthik Reddy', role: 'DS' },
  AD: { id: 'u-ad', name: 'Meera Krishnan', role: 'AD' },
};

export const initials = (name: string) =>
  name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();

export const can = (role: RoleId, cap: Role['can'][number]) => ROLES[role].can.includes(cap);
