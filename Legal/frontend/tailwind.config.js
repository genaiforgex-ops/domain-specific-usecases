/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: "var(--color-accent)",
          bright: "var(--color-accent-bright)",
          foreground: "#ffffff",
        },
        success: "var(--color-success)",
        error: "var(--color-error)",
        warning: "var(--color-warning)",
        label: {
          DEFAULT: "var(--color-label)",
          secondary: "var(--color-label-secondary)",
          tertiary: "var(--color-label-tertiary)",
        },
        bg: {
          DEFAULT: "var(--color-bg)",
          secondary: "var(--color-bg-secondary)",
          accent: "var(--color-bg-accent)",
        },
        ink: {
          DEFAULT: "var(--color-ink)",
          soft: "var(--color-ink-soft)",
        },
        paper: "var(--color-paper)",
        separator: "var(--color-separator)",
        // Legacy brand scale — maps to accent for gradual migration
        brand: {
          DEFAULT: "var(--color-accent)",
          50: "color-mix(in srgb, var(--color-accent) 8%, white)",
          100: "color-mix(in srgb, var(--color-accent) 15%, white)",
          200: "color-mix(in srgb, var(--color-accent) 25%, white)",
          300: "color-mix(in srgb, var(--color-accent) 40%, white)",
          400: "color-mix(in srgb, var(--color-accent) 60%, white)",
          500: "var(--color-accent)",
          600: "var(--color-accent)",
          700: "var(--color-accent)",
          800: "color-mix(in srgb, var(--color-accent) 85%, black)",
          900: "color-mix(in srgb, var(--color-accent) 70%, black)",
          950: "color-mix(in srgb, var(--color-accent) 50%, black)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        display: ["var(--font-display)"],
      },
      fontSize: {
        "large-title": ["var(--text-large-title)", { lineHeight: "1.2", fontWeight: "600" }],
        "title-1": ["var(--text-title-1)", { lineHeight: "1.25", fontWeight: "600" }],
        "title-2": ["var(--text-title-2)", { lineHeight: "1.3", fontWeight: "600" }],
        "title-3": ["var(--text-title-3)", { lineHeight: "1.35", fontWeight: "600" }],
        headline: ["var(--text-headline)", { lineHeight: "1.4", fontWeight: "600" }],
        body: ["var(--text-body)", { lineHeight: "1.47", fontWeight: "400" }],
        callout: ["var(--text-callout)", { lineHeight: "1.45", fontWeight: "400" }],
        subheadline: ["var(--text-subheadline)", { lineHeight: "1.4", fontWeight: "400" }],
        footnote: ["var(--text-footnote)", { lineHeight: "1.35", fontWeight: "400" }],
        caption: ["var(--text-caption)", { lineHeight: "1.3", fontWeight: "400" }],
      },
      spacing: {
        1: "var(--space-1)",
        2: "var(--space-2)",
        3: "var(--space-3)",
        4: "var(--space-4)",
        5: "var(--space-5)",
        6: "var(--space-6)",
        7: "var(--space-7)",
        8: "var(--space-8)",
        tap: "var(--tap-min)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-2xl)",
        full: "var(--radius-full)",
      },
      transitionTimingFunction: {
        standard: "var(--ease-standard)",
        decelerate: "var(--ease-decelerate)",
        accelerate: "var(--ease-accelerate)",
        spring: "var(--ease-spring)",
      },
      transitionDuration: {
        fast: "var(--duration-fast)",
        base: "var(--duration-base)",
        slow: "var(--duration-slow)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(100%)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "slide-out-right": {
          "0%": { opacity: "1", transform: "translateX(0)" },
          "100%": { opacity: "0", transform: "translateX(100%)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.97)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
        "genie-breathe": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.92" },
          "50%": { transform: "scale(1.04)", opacity: "1" },
        },
        "genie-rise": {
          "0%": { opacity: "0", transform: "translateY(18px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "genie-glow": {
          "0%, 100%": { opacity: "0.45", transform: "scale(1)" },
          "50%": { opacity: "0.75", transform: "scale(1.08)" },
        },
        "composer-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(47, 74, 184, 0)" },
          "50%": { boxShadow: "0 0 0 4px rgba(47, 74, 184, 0.08)" },
        },
      },
      animation: {
        "fade-in": "fade-in var(--duration-base) var(--ease-decelerate) both",
        "slide-up": "slide-up var(--duration-slow) var(--ease-decelerate) both",
        "slide-in-right": "slide-in-right var(--duration-slow) var(--ease-decelerate) both",
        "slide-out-right": "slide-out-right var(--duration-slow) var(--ease-accelerate) both",
        "scale-in": "scale-in var(--duration-base) var(--ease-spring) both",
        shimmer: "shimmer 2.4s linear infinite",
        "pulse-soft": "pulse-soft 2s ease-in-out infinite",
        "genie-breathe": "genie-breathe 4.5s ease-in-out infinite",
        "genie-rise": "genie-rise 0.7s var(--ease-decelerate) both",
        "genie-glow": "genie-glow 5s ease-in-out infinite",
        "composer-pulse": "composer-pulse 3.2s ease-in-out infinite",
      },
      boxShadow: {
        card: "0 1px 2px rgba(14, 20, 36, 0.04), 0 0 0 1px rgba(14, 20, 36, 0.04)",
        subtle: "0 0 0 0.5px var(--color-separator)",
        atelier: "0 12px 40px rgba(14, 20, 36, 0.18)",
        "atelier-soft": "0 8px 28px rgba(14, 20, 36, 0.08)",
      },
    },
  },
  plugins: [],
};
