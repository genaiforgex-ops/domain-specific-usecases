import type { Config } from 'tailwindcss';

/**
 * Tokens mirror .claude/design_guidelines.md (Apple HIG + Liquid Glass, 2025).
 * Colors reference CSS variables so light/dark/contrast switch automatically.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        accent: 'var(--color-accent)',
        'accent-soft': 'var(--color-accent-soft)',
        success: 'var(--color-success)',
        error: 'var(--color-error)',
        warning: 'var(--color-warning)',
        label: 'var(--color-label)',
        'label-secondary': 'var(--color-label-secondary)',
        'label-tertiary': 'var(--color-label-tertiary)',
        bg: 'var(--color-bg)',
        'bg-secondary': 'var(--color-bg-secondary)',
        'bg-tertiary': 'var(--color-bg-tertiary)',
        separator: 'var(--color-separator)',
        'fill-quaternary': 'var(--color-fill-quaternary)',
      },
      fontFamily: {
        sans: [
          'DM Sans',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Helvetica Neue"',
          'system-ui',
          'sans-serif',
        ],
        display: ['Syne', 'DM Sans', 'system-ui', 'sans-serif'],
        mono: ['"SF Mono"', 'ui-monospace', 'Menlo', 'monospace'],
      },
      fontSize: {
        display: ['clamp(40px, 6vw, 60px)', { lineHeight: '1.02', letterSpacing: '-0.035em' }],
        'large-title': ['34px', { lineHeight: '40px', letterSpacing: '-0.02em' }],
        'title-1': ['28px', { lineHeight: '34px', letterSpacing: '-0.02em' }],
        'title-2': ['22px', { lineHeight: '28px', letterSpacing: '-0.01em' }],
        'title-3': ['20px', { lineHeight: '25px', letterSpacing: '-0.01em' }],
        headline: ['17px', { lineHeight: '22px', letterSpacing: '-0.01em', fontWeight: '600' }],
        body: ['17px', { lineHeight: '22px' }],
        callout: ['16px', { lineHeight: '21px' }],
        subheadline: ['15px', { lineHeight: '20px' }],
        footnote: ['13px', { lineHeight: '18px' }],
        caption: ['12px', { lineHeight: '16px' }],
        caption2: ['11px', { lineHeight: '13px' }],
      },
      spacing: {
        '1': '4px', '2': '8px', '3': '12px', '4': '16px',
        '5': '24px', '6': '32px', '7': '40px', '8': '48px',
      },
      // Monday uses tight radii — 4px controls, 8px cards, 12px dialogs.
      borderRadius: {
        sm: '4px', md: '6px', lg: '8px', xl: '10px', '2xl': '12px', full: '9999px',
      },
      transitionTimingFunction: {
        standard: 'cubic-bezier(0.4, 0.0, 0.2, 1)',
        decelerate: 'cubic-bezier(0.0, 0.0, 0.2, 1)',
        accelerate: 'cubic-bezier(0.4, 0.0, 1, 1)',
        spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      transitionDuration: { fast: '150ms', base: '250ms', slow: '350ms' },
      boxShadow: {
        card: '0 1px 2px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.04)',
        elevated: '0 8px 30px rgba(0,0,0,0.10), 0 2px 6px rgba(0,0,0,0.05)',
        glass: '0 1px 0 rgba(255,255,255,0.5) inset, 0 8px 32px rgba(0,0,0,0.10)',
      },
      backdropBlur: { glass: '20px' },
    },
  },
  plugins: [],
} satisfies Config;
