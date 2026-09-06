/** Friendly names for the ad formats, keyed by the banner template's size name —
 *  the performance sizes plus the WhatsApp / RCS / Rich Push messaging formats.
 *  Shared by the Designer's export picker and the Design Studio's crop guides so
 *  a format is never called two different things. */
export const AD_SIZE_LABELS: Record<string, string> = {
  square: 'Square',
  story: 'Story',
  portrait: 'Portrait',
  landscape: 'Landscape',
  link: 'Link / Feed',
  WA: 'WhatsApp',
  RCS: 'RCS',
  RPN: 'Rich Push',
};
