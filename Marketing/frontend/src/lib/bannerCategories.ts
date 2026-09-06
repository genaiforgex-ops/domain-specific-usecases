// Banner template *categories* — the family a Product Lead picks at brief
// creation (locking which templates the Designer may work from). Categories are
// data-driven: they're whatever distinct `category` slugs the template gallery
// returns. This module only supplies friendly labels/descriptions and the
// grouping helper, so adding a new category server-side needs no code change
// (it falls back to a prettified slug).

import type { BannerTemplateSummary } from './types';

const CATEGORY_META: Record<string, { label: string; blurb: string }> = {
  performance: {
    label: 'Performance statics',
    blurb: 'On-brand performance-ad creatives across the standard ad sizes.',
  },
  messaging: {
    label: 'WhatsApp / RCS / RPN',
    blurb: 'Conversational messaging banners — copy left, subject composed right.',
  },
};

const prettify = (slug: string) =>
  slug.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

export const categoryLabel = (slug: string): string =>
  CATEGORY_META[slug]?.label ?? prettify(slug);

export const categoryBlurb = (slug: string): string => CATEGORY_META[slug]?.blurb ?? '';

export interface BannerCategory {
  slug: string;
  label: string;
  blurb: string;
  count: number; // how many templates the category holds
}

/** Distinct categories present in the gallery, in gallery order (default first). */
export function categoriesFromTemplates(templates: BannerTemplateSummary[]): BannerCategory[] {
  const order: string[] = [];
  const counts = new Map<string, number>();
  for (const t of templates) {
    if (!counts.has(t.category)) order.push(t.category);
    counts.set(t.category, (counts.get(t.category) ?? 0) + 1);
  }
  return order.map((slug) => ({
    slug,
    label: categoryLabel(slug),
    blurb: categoryBlurb(slug),
    count: counts.get(slug) ?? 0,
  }));
}
