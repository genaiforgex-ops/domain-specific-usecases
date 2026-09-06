import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// The design system replaces Tailwind's font-size scale with named HIG sizes
// (see tailwind.config.ts). tailwind-merge doesn't know them, so it wrongly
// treats e.g. `text-footnote` as a text *color* and, when it follows a real
// colour in the class list, drops the colour (a filled button then inherits the
// parent's dark text). Registering them as font sizes keeps size and colour in
// separate groups so both survive a merge.
const FONT_SIZES = [
  'display', 'large-title', 'title-1', 'title-2', 'title-3', 'headline',
  'body', 'callout', 'subheadline', 'footnote', 'caption', 'caption2',
];

const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: FONT_SIZES }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
