import type { DesignQueueItem } from './types';

// The four states a brief moves through in the Designer's hands, from arrival to
// shipped. Used by both the Designer dashboard and the My Assets list so they
// describe progress identically.
export type DesignStatus = 'not_started' | 'in_progress' | 'ready' | 'done';

export function designStatus(b: DesignQueueItem): DesignStatus {
  // The queue this reads from only ever holds briefs still in the design stage
  // (see list_design_queue), so a brief with figma_file_url set here has been
  // exported but NOT yet sent for review — still 'ready', not 'done'.
  if (b.creative_count > 0 && b.approved_count >= b.creative_count) return 'ready'; // all images approved
  if (b.image_count > 0) return 'in_progress'; // some images generated, not all approved
  return 'not_started'; // handed off, no images yet
}

interface StatusMeta {
  label: string; // short pill text
  hue: string; // pill / accent colour
  eyebrow: string; // dashboard hero eyebrow
  cta: string; // what to do next
  order: number; // priority sort — lower surfaces first (closest to done)
}

// Ordered so the work queue shows the brief closest to shipping first: a brief
// whose images are all approved (one click from done) outranks one mid-review,
// which outranks one not yet started.
export const DESIGN_STATUS: Record<DesignStatus, StatusMeta> = {
  ready: {
    label: 'Ready to send',
    hue: 'var(--color-accent)',
    eyebrow: 'Ready to ship',
    cta: 'Export to Figma & send for review',
    order: 0,
  },
  in_progress: {
    label: 'In progress',
    hue: 'var(--color-warning)',
    eyebrow: 'Pick up where you left off',
    cta: 'Review & approve the hero images',
    order: 1,
  },
  not_started: {
    label: 'Not started',
    hue: 'var(--color-label-tertiary)',
    eyebrow: 'New on your desk',
    cta: 'Generate the banner hero images',
    order: 2,
  },
  done: {
    label: 'Shipped',
    hue: 'var(--color-success)',
    eyebrow: 'Done',
    cta: 'View the exported Figma file',
    order: 3,
  },
};

/** A one-line progress summary, e.g. "4 / 6 images approved". */
export function designProgress(b: DesignQueueItem): string {
  if (b.figma_file_url) return `${b.creative_count} creative${b.creative_count === 1 ? '' : 's'} exported`;
  if (b.image_count === 0) return `${b.creative_count} creative${b.creative_count === 1 ? '' : 's'} awaiting images`;
  return `${b.approved_count} / ${b.image_count} image${b.image_count === 1 ? '' : 's'} approved`;
}
