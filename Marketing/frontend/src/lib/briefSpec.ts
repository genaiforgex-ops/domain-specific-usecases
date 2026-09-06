import type { BriefFieldKey, BriefForm, BriefSize } from './types';

// Declarative spec for the three intake templates. Small & Medium share one
// set of sections; Large has its own. The form, validation, and read-only
// detail view all render from this — one source of truth for the brief shape.

export type FieldKind = 'text' | 'textarea' | 'date';

export interface FieldSpec {
  key: BriefFieldKey;
  label: string;
  kind: FieldKind;
  mandatory?: boolean;
  placeholder?: string;
  help?: string;
  /** Filled by the system, never typed in — rendered read-only. The server derives
   *  the value on save (see autoDates), so it can't be mandatory or missing. */
  auto?: boolean;
}

/** Working days between a brief being raised and when it's expected back. Mirrors
 *  the server's brief_service.EXPECTED_TURNAROUND_DAYS. */
export const EXPECTED_TURNAROUND_DAYS = 3;

// Local calendar date as YYYY-MM-DD. Deliberately not toISOString(), which shifts
// to UTC and lands on yesterday for any evening in IST.
const isoDate = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

/**
 * The brief's two automatic dates: the day it was raised and the day it's expected
 * back, EXPECTED_TURNAROUND_DAYS later. `from` re-derives the expected date from an
 * existing brief date; omit it for a new brief (today).
 *
 * The server is authoritative — brief_service.stamp_dates applies the same rule on
 * every save. This exists so the form shows what is about to be saved.
 */
export function autoDates(from?: string | null): { brief_date: string; expected_date: string } {
  const raised = from ? new Date(`${from}T00:00:00`) : new Date();
  const expected = new Date(raised);
  expected.setDate(expected.getDate() + EXPECTED_TURNAROUND_DAYS);
  return { brief_date: isoDate(raised), expected_date: isoDate(expected) };
}

/** The form minus the system-owned fields. The API doesn't accept the two dates —
 *  they're held in the form only so the author can see them — so they're dropped
 *  here rather than sent and silently ignored. */
export function submittableFields(form: BriefForm): BriefForm {
  const { brief_date: _b, expected_date: _e, ...rest } = form;
  return rest;
}

export interface Section {
  title: string;
  fields: FieldSpec[];
}

export const SIZE_META: Record<BriefSize, { label: string; blurb: string }> = {
  small: { label: 'Small', blurb: 'Quick task brief — single asset or channel.' },
  medium: { label: 'Medium', blurb: 'Standard task brief — a few platforms.' },
  large: { label: 'Large', blurb: 'Full campaign brief — strategy, persona, deliverables.' },
};

const SMALL_MED: Section[] = [
  {
    title: '1 · Project Overview',
    fields: [
      { key: 'project_name', label: 'Project Name', kind: 'text' },
      { key: 'product_name', label: 'Product Name', kind: 'text', mandatory: true },
      { key: 'owner_name', label: 'Owner', kind: 'text', mandatory: true },
      { key: 'brief_date', label: 'Date', kind: 'date', auto: true, help: 'Today — set automatically.' },
      {
        key: 'expected_date',
        label: 'Expected Date',
        kind: 'date',
        auto: true,
        help: `${EXPECTED_TURNAROUND_DAYS} days after the brief date — set automatically.`,
      },
      { key: 'sm_go_live_timeline', label: 'Go-live Timeline', kind: 'text', mandatory: true },
      {
        key: 'sm_one_line_summary',
        label: 'One-line summary',
        kind: 'textarea',
        mandatory: true,
        help: 'What are we building / launching and why?',
      },
    ],
  },
  {
    title: '2 · Objective (Why This Matters)',
    fields: [
      {
        key: 'sm_primary_goal',
        label: 'Primary goal',
        kind: 'textarea',
        mandatory: true,
        placeholder: 'e.g. drive early-access registrations / increase SB upgrades / collect feedback',
      },
      { key: 'sm_business_kpi', label: 'Business KPI impacted', kind: 'textarea' },
      {
        key: 'sm_strategic_context',
        label: 'Strategic context',
        kind: 'textarea',
        placeholder: 'launch, campaign, leadership priority, etc.',
      },
    ],
  },
  {
    title: '3 · Target Audience',
    fields: [
      {
        key: 'sm_audience_who',
        label: 'Who is this for?',
        kind: 'textarea',
        mandatory: true,
        placeholder: 'Internal / Public CUG / Existing customers / New users',
      },
      {
        key: 'sm_audience_segment',
        label: 'Segment / Cohort specifics',
        kind: 'textarea',
        mandatory: true,
        placeholder: 'whitelisted users, high-balance customers, etc.',
      },
      { key: 'sm_audience_exclusions', label: 'Any exclusions?', kind: 'textarea' },
      {
        key: 'sm_mandatories_tnc',
        label: 'Mandatories & T&C to be used',
        kind: 'textarea',
        mandatory: true,
      },
    ],
  },
  {
    title: '4 · Platforms, Dimensions & Specifications',
    fields: [
      {
        key: 'sm_platforms',
        label: 'Platforms',
        kind: 'textarea',
        mandatory: true,
        placeholder: 'Mobile App, Web, WhatsApp, RCS, IG, LinkedIn…',
      },
      {
        key: 'sm_dimensions_specs',
        label: 'Dimensions & Specifications',
        kind: 'textarea',
        mandatory: true,
        help: 'e.g. WhatsApp 1125×600 (1.91:1) · RCS 1440×720 or 1440×448 (16:9 / 2:1) · Notification title ≤45, body ≤120',
      },
      {
        key: 'sm_final_ui_screen',
        label: 'Final UI screen',
        kind: 'textarea',
        help: 'Link or note — to be shared along with the brief',
      },
      { key: 'sm_samples_references', label: 'Samples / Examples / References', kind: 'textarea' },
    ],
  },
];

const LARGE: Section[] = [
  {
    title: '1 · Project Overview',
    fields: [
      { key: 'project_name', label: 'Project Name', kind: 'text' },
      { key: 'product_name', label: 'Product Name', kind: 'text', mandatory: true },
      { key: 'owner_name', label: 'Product Owner', kind: 'text', mandatory: true },
      {
        key: 'brief_date',
        label: 'Date of Brief Creation',
        kind: 'date',
        auto: true,
        help: 'Today — set automatically.',
      },
      {
        key: 'expected_date',
        label: 'Expected Date',
        kind: 'date',
        auto: true,
        help: `${EXPECTED_TURNAROUND_DAYS} days after the brief date — set automatically.`,
      },
      { key: 'lg_project_purpose', label: 'Project Purpose', kind: 'textarea' },
    ],
  },
  {
    title: '2 · Objectives & Measurement',
    fields: [
      { key: 'lg_business_objective', label: 'Overall Business Objective', kind: 'textarea' },
      { key: 'lg_marketing_objective', label: 'Marketing Objective', kind: 'textarea', mandatory: true },
      { key: 'lg_communication_objective', label: 'Communication Objective', kind: 'textarea', mandatory: true },
      {
        key: 'lg_effectiveness_metric',
        label: 'Effectiveness metric',
        kind: 'textarea',
        help: 'How will we measure the effectiveness of the project?',
      },
    ],
  },
  {
    title: '3 · Target Audience / Persona',
    fields: [
      {
        key: 'lg_ideal_customer',
        label: 'Ideal customer',
        kind: 'textarea',
        mandatory: true,
        help: 'Describe their behavior, habits and interests in detail.',
      },
      { key: 'lg_demo_age', label: 'Age', kind: 'text' },
      { key: 'lg_demo_gender', label: 'Gender', kind: 'text' },
      { key: 'lg_demo_top_cities', label: 'Top cities', kind: 'text' },
      { key: 'lg_goals_motivations', label: 'Goals & Motivations', kind: 'textarea' },
    ],
  },
  {
    title: '4 · Product, Category & Consumer Insights',
    fields: [
      { key: 'lg_category_insight', label: 'Category insight', kind: 'textarea' },
      { key: 'lg_conservative_target', label: 'Conservative target', kind: 'textarea' },
      { key: 'lg_aspirational_target', label: 'Aspirational target', kind: 'textarea' },
      {
        key: 'lg_product_insight',
        label: 'Product Insight',
        kind: 'textarea',
        mandatory: true,
        help: 'What the product is, why it exists, market sentiment, etc.',
      },
      { key: 'lg_key_markets', label: 'Key markets', kind: 'textarea' },
      { key: 'lg_competition', label: 'Competition', kind: 'textarea', mandatory: true },
    ],
  },
  {
    title: '5 · Product and Features',
    fields: [
      { key: 'lg_product_features', label: 'Products / service features on offer', kind: 'textarea', mandatory: true },
      { key: 'lg_key_features_deliverables', label: 'Key features / deliverables of each', kind: 'textarea', mandatory: true },
      { key: 'lg_unique_offerings', label: 'Unique offerings vs competition', kind: 'textarea', mandatory: true },
    ],
  },
  {
    title: '6 · Think, Feel, Do',
    fields: [
      { key: 'lg_think_before', label: 'Think — before communication', kind: 'textarea' },
      { key: 'lg_think_after', label: 'Think — after communication', kind: 'textarea' },
      { key: 'lg_feel_before', label: 'Feel — before communication', kind: 'textarea' },
      { key: 'lg_feel_after', label: 'Feel — after communication', kind: 'textarea' },
      { key: 'lg_do_before', label: 'Do — before communication', kind: 'textarea' },
      { key: 'lg_do_after', label: 'Do — after communication', kind: 'textarea' },
    ],
  },
  {
    title: '7 · Other Considerations',
    fields: [
      { key: 'lg_cultural_sensitivity', label: 'Cultural Sensitivity', kind: 'textarea' },
      { key: 'lg_languages', label: 'Languages', kind: 'textarea', mandatory: true },
      { key: 'lg_other_considerations', label: 'Others', kind: 'textarea' },
    ],
  },
  {
    title: '8 · Deliverables',
    fields: [
      {
        key: 'lg_deliverables',
        label: 'Deliverables',
        kind: 'textarea',
        mandatory: true,
        help: 'List all deliverables — sizes, format, creative placements, deadlines.',
      },
    ],
  },
];

export const sectionsFor = (size: BriefSize): Section[] => (size === 'large' ? LARGE : SMALL_MED);

/** Mandatory field keys still empty in the form — mirrors the server check. */
export function missingRequired(size: BriefSize, form: Record<string, string | undefined>): FieldSpec[] {
  return sectionsFor(size)
    .flatMap((s) => s.fields)
    .filter((f) => f.mandatory && !form[f.key]?.trim());
}
