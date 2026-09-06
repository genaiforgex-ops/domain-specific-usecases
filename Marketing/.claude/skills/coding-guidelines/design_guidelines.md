# Apple-Style Design Guidelines

A practical reference for building UI that feels native to Apple's ecosystem — smooth, clear, and aesthetic. Based on Apple's Human Interface Guidelines (HIG) and the 2025 **Liquid Glass** design language (iOS/iPadOS/macOS 26). Use this as the standard any new feature in your app should pass.

> **How to read this:** The principles are the *why*. The tokens (colors, type, spacing, motion) are the *what*. Build features against the tokens, sanity-check them against the principles, then run the checklist at the bottom before shipping.

---

## 1. Core philosophy

Three foundational ideas have anchored Apple design for a decade, and the 2025 system layers three more on top.

**The timeless three:**

- **Clarity** — Text is legible at every size, icons are precise, content is the focus. Nothing decorative competes with what the user came for.
- **Deference** — The UI gets out of the way. Chrome (toolbars, tab bars, backgrounds) recedes so content leads. Color, motion, and material support content rather than upstaging it.
- **Depth** — Layering and realistic motion convey hierarchy and give the interface a sense of place. Users always know where they are and how they got there.

**The Liquid Glass three (2025):**

- **Hierarchy** — Importance is communicated through *depth* — varying transparency, refraction, and visual weight — not just size or color. Controls "float" above and elevate the content beneath them.
- **Harmony** — Every element, from the smallest control to the largest surface, is designed in relation to the whole. Consistent geometry, concentric shapes, and a unified color family make the interface feel like one coherent material.
- **Consistency** — The same patterns adapt across window sizes, devices, and contexts. Use platform-standard navigation and components; don't reinvent system chrome.

**The one rule that drives the look:** *Content leads, chrome recedes.* If you remember nothing else, remember that.

---

## 2. Color

### Principles

- **Design to semantic roles, not raw hex.** Use roles like `label`, `secondaryLabel`, `systemBackground`, `systemBlue`. These adapt automatically to light mode, dark mode, and increased-contrast mode. Hardcoding a hex value breaks that adaptation.
- **Reserve color for action.** Limit your accent (primary) color to interactive elements — buttons, links, switches, selected states. This trains users that "colored = tappable."
- **Color never carries meaning alone.** Always pair it with a label, icon, or shape so colorblind users aren't excluded.
- **One primary accent.** `systemBlue` is Apple's default. Pick a single accent for your brand and use it with restraint.

### Reference values (light mode)

These are approximate Apple system colors for the **default light appearance**. Treat them as starting points — your implementation should swap them for dark/contrast variants via semantic tokens.

| Role | Light hex | Use |
|------|-----------|-----|
| systemBlue (accent) | `#007AFF` | Primary actions, links, selection |
| systemGreen | `#34C759` | Success, confirmation |
| systemRed | `#FF3B30` | Errors, destructive actions |
| systemOrange | `#FF9500` | Warnings |
| systemYellow | `#FFCC00` | Caution / highlights |
| systemIndigo | `#5856D6` | Secondary accent |
| systemPink | `#FF2D55` | Accent variety |
| label (primary text) | `#000000` (≈100%) | Headings, body |
| secondaryLabel | `#3C3C43` (≈60%) | Subtitles, supporting text |
| tertiaryLabel | `#3C3C43` (≈30%) | Placeholder, disabled |
| systemBackground | `#FFFFFF` | Base background |
| secondarySystemBackground | `#F2F2F7` | Grouped/cards background |
| separator | `#3C3C43` (≈29%) | Hairline dividers |

### Reference values (dark mode)

| Role | Dark hex |
|------|----------|
| systemBlue | `#0A84FF` |
| systemGreen | `#30D158` |
| systemRed | `#FF453A` |
| systemOrange | `#FF9F0A` |
| label | `#FFFFFF` |
| secondaryLabel | `#EBEBF5` (≈60%) |
| systemBackground | `#000000` |
| secondarySystemBackground | `#1C1C1E` |

> Apple's full system color family was subtly re-tuned in 2025 to improve hue differentiation while staying in harmony with Liquid Glass. Don't over-saturate; the optimistic-but-restrained feel comes from these calibrated hues.

---

## 3. Typography

### Principles

- **Use the system font.** SF Pro is Apple's typeface. Lean on its weights and sizes for hierarchy instead of adding a second display font. On the web, the system font stack (`-apple-system, BlinkMacSystemFont, "SF Pro", ...`) gives you this for free on Apple devices.
- **Weight and size carry hierarchy** — bigger and bolder for titles and key data; smaller and lighter pushes secondary info back.
- **17pt is the body legibility floor.** Don't go below 11pt for anything.
- **Support Dynamic Type.** Text should scale with the user's accessibility settings; use relative units (rem/em, or the text styles below) rather than fixed pixels where possible.
- **Optical sizing:** SF Pro Text for ≤19pt, SF Pro Display for ≥20pt (the system handles this automatically when you use the named text styles).
- 2025 refinement: titles in key moments (alerts, onboarding) are now **bolder and left-aligned** for clarity.

### Type scale (iOS text styles)

| Style | Size / Weight | Use |
|-------|---------------|-----|
| Large Title | 34pt / Regular–Bold | Top-level screen titles |
| Title 1 | 28pt / Regular | Section headers |
| Title 2 | 22pt / Regular | Sub-section headers |
| Title 3 | 20pt / Regular | Card titles |
| Headline | 17pt / Semibold | Emphasized body, list headers |
| Body | 17pt / Regular | Default body text |
| Callout | 16pt / Regular | Secondary body |
| Subheadline | 15pt / Regular | Supporting text |
| Footnote | 13pt / Regular | Captions, metadata |
| Caption 1 | 12pt / Regular | Small labels |
| Caption 2 | 11pt / Regular | Minimum readable size |

Fonts: **SF Pro** (sans, default), **SF Mono** (code/data), **New York** (serif, when you want an alternative editorial voice). SF Pro Rounded pairs with soft/rounded UI.

---

## 4. Spacing & layout

### Principles

- **8pt grid with 4pt subdivisions.** Use multiples of 8 (8, 16, 24, 32, 40, 48…) for padding, margins, and gaps, with 4pt for fine adjustments. *(Note: this is a widely used convention that matches Apple's output — Apple doesn't formally brand it the way Material Design does — but it's reliable.)*
- **Minimum 44×44pt tap targets.** Every interactive control, including secondary actions and icon-only buttons. This has been an Apple rule since the original iPhone.
- **Whitespace is an action.** Use generous, consistent spacing to group related elements and separate sections. Breathing room makes content the star.
- **Respect safe areas.** Keep content clear of notches, home indicators, and rounded screen corners.
- **Adapt to window size.** Layouts should reflow gracefully across sizes and orientations — don't lock to one width.

### Spacing scale

| Token | Value |
|-------|-------|
| space-1 | 4px |
| space-2 | 8px |
| space-3 | 12px |
| space-4 | 16px |
| space-5 | 24px |
| space-6 | 32px |
| space-7 | 40px |
| space-8 | 48px |

---

## 5. Corner radius & concentricity

Rounded geometry is core to the Apple feel, and 2025 leans into it hard — capsule shapes support natural concentricity.

**The concentric rule:** an inner element's radius plus its padding should equal the outer container's radius, so nested rounded shapes stay visually parallel.
`inner_radius + padding = outer_radius` (e.g. 8px inner + 8px padding = 16px outer).

| Token | Value | Use |
|-------|-------|-----|
| radius-sm | 8px | Small buttons, tags, inputs |
| radius-md | 12px | Standard buttons, list rows |
| radius-lg | 16px | Cards |
| radius-xl | 20px | Sheets, large cards |
| radius-2xl | 24px | Modals |
| radius-full | 9999px | Capsules / pills |

---

## 6. Materials & Liquid Glass

The signature look of 2025. Liquid Glass is a translucent layer that floats above content, refracts light, and reacts to motion and input — like a real pane of glass hovering over what's beneath.

### When to use it

- **Navigation and control layers:** toolbars, tab bars, sidebars, sheets, menus, floating controls. These are the "chrome" that should sit *above* content.
- **Not for content itself.** Don't make your main content panes glass — that hurts readability and performance.

### How to use it well

- **Transparency is a tool for depth, not decoration.** Use it sparingly and purposefully.
- **Keep text legible across dynamic backgrounds.** Add a subtle scrim/tint behind text on glass if contrast drops.
- **Use blur + parallax sparingly** so motion informs rather than distracts.
- **Watch performance and accessibility** — over-applied glass is costly on both. Test on real backgrounds.

### Material levels (blur intensity, light to heavy)

`ultraThin → thin → regular → thick → chrome`. Thicker = more obscured background, more readable foreground.

### Web approximation (CSS)

```css
.glass {
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 0.5px solid rgba(255, 255, 255, 0.3);
  border-radius: 16px;
}
.glass-dark {
  background: rgba(30, 30, 30, 0.6);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
}
```

---

## 7. Motion & animation

Smoothness comes from *physics-based, restrained* motion — not lots of effects. Apple animations feel like objects with real weight and momentum.

### Principles

- **Motion conveys meaning.** Transitions show where things come from and go to (a sheet slides up because it lives below; a detail zooms from the cell you tapped).
- **Spring physics over linear timing.** Apple's native animations are spring-based — gentle overshoot and settle, not robotic linear interpolation.
- **Fast and subtle.** Most UI transitions are 200–400ms. Micro-interactions (button press, toggle) are 100–200ms. Longer than ~500ms feels sluggish.
- **Respect Reduce Motion.** When the user enables it, disable elastic/parallax effects and fall back to simple cross-fades. This is mandatory, not optional.
- **Less is more.** Scattered animation reads as "AI-generated" or amateur. One well-orchestrated moment beats ten small effects.

### Standard easing curves

| Name | cubic-bezier | Use |
|------|--------------|-----|
| Standard (ease-in-out) | `cubic-bezier(0.4, 0.0, 0.2, 1)` | Most transitions |
| Decelerate (ease-out) | `cubic-bezier(0.0, 0.0, 0.2, 1)` | Elements entering |
| Accelerate (ease-in) | `cubic-bezier(0.4, 0.0, 1, 1)` | Elements leaving |
| Spring (approx) | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Playful pop / press feedback |

### Durations

| Token | Value | Use |
|-------|-------|-----|
| duration-fast | 150ms | Taps, toggles, hovers |
| duration-base | 250ms | Standard transitions |
| duration-slow | 350ms | Sheets, modals, page changes |

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 8. Component patterns

**Buttons** — Three tiers: *filled* (primary, accent background, one per view ideally), *tinted/gray* (secondary), *plain/text* (tertiary). 44pt min height, capsule or `radius-md`, clear pressed state (scale to ~0.97 + slight dim).

**Cards** — `secondarySystemBackground`, `radius-lg`, generous internal padding (16–24px), subtle shadow or a hairline border — not both heavy.

**Inputs** — `radius-md`, clear focus ring in the accent color, 44pt min height, visible label (not placeholder-as-label), inline validation with text + icon (never color alone).

**Lists / rows** — Full-width separators inset to align with text, chevron for navigation, 44pt min row height.

**Sheets & modals** — Slide up from bottom, rounded top corners (`radius-xl`), a grabber handle, dim/blur the background. Glass material on the sheet chrome.

**Icons** — Use SF Symbols (or a consistent outlined set that matches your text weight). Match icon weight to adjacent text weight. Avoid photorealistic detail.

**Navigation** — Use standard tab bars / nav patterns; don't replace system chrome with custom equivalents.

---

## 9. Accessibility (non-negotiable)

Treat these as functional requirements, not nice-to-haves — a violation is a bug.

- **Contrast:** 4.5:1 for normal text, 3:1 for large text (WCAG AA).
- **Tap targets:** 44×44pt minimum, everywhere.
- **Dynamic Type:** text scales with user settings.
- **Reduce Motion:** honored — no forced parallax/elastic effects.
- **Reduce Transparency:** when on, make glass frostier/more opaque so content stays readable.
- **Increased Contrast:** support a higher-contrast color variant.
- **VoiceOver:** every interactive element has a label, including icon-only buttons.
- **Color independence:** meaning is never conveyed by color alone.

---

## 10. Pre-ship checklist

Run this against any new feature before it's done:

- [ ] Body text is SF/system font, ≥17pt, with Dynamic Type enabled
- [ ] Color uses semantic roles; accent reserved for interactive elements
- [ ] All tap targets ≥ 44×44pt
- [ ] Spacing follows the 8pt grid
- [ ] Corner radii follow the concentric rule
- [ ] Glass material used only on chrome, never on primary content
- [ ] Transitions use spring/standard easing, ≤ ~400ms
- [ ] Reduce Motion and Reduce Transparency are respected
- [ ] Contrast hits 4.5:1 (normal) / 3:1 (large)
- [ ] VoiceOver labels on every interactive element
- [ ] Color never carries meaning alone
- [ ] Navigation uses standard platform patterns, not custom chrome
- [ ] Layout adapts gracefully across window sizes
- [ ] One bold signature element; everything else stays quiet

---

## 11. Drop-in CSS design tokens

Copy this into your stylesheet and reference the variables everywhere. Includes automatic dark-mode switching.

```css
:root {
  /* Accent & status */
  --color-accent: #007AFF;
  --color-success: #34C759;
  --color-error: #FF3B30;
  --color-warning: #FF9500;

  /* Text */
  --color-label: rgba(0, 0, 0, 1);
  --color-label-secondary: rgba(60, 60, 67, 0.6);
  --color-label-tertiary: rgba(60, 60, 67, 0.3);

  /* Backgrounds */
  --color-bg: #FFFFFF;
  --color-bg-secondary: #F2F2F7;
  --color-separator: rgba(60, 60, 67, 0.29);

  /* Glass */
  --glass-bg: rgba(255, 255, 255, 0.6);
  --glass-border: rgba(255, 255, 255, 0.3);
  --glass-blur: blur(20px) saturate(180%);

  /* Typography */
  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  --font-mono: "SF Mono", ui-monospace, Menlo, monospace;
  --text-large-title: 34px;
  --text-title-1: 28px;
  --text-title-2: 22px;
  --text-title-3: 20px;
  --text-headline: 17px;
  --text-body: 17px;
  --text-callout: 16px;
  --text-subheadline: 15px;
  --text-footnote: 13px;
  --text-caption: 12px;

  /* Spacing (8pt grid) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 40px;
  --space-8: 48px;

  /* Radius */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 20px;
  --radius-2xl: 24px;
  --radius-full: 9999px;

  /* Motion */
  --ease-standard: cubic-bezier(0.4, 0.0, 0.2, 1);
  --ease-decelerate: cubic-bezier(0.0, 0.0, 0.2, 1);
  --ease-accelerate: cubic-bezier(0.4, 0.0, 1, 1);
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --duration-fast: 150ms;
  --duration-base: 250ms;
  --duration-slow: 350ms;

  /* Touch target */
  --tap-min: 44px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-accent: #0A84FF;
    --color-success: #30D158;
    --color-error: #FF453A;
    --color-warning: #FF9F0A;
    --color-label: rgba(255, 255, 255, 1);
    --color-label-secondary: rgba(235, 235, 245, 0.6);
    --color-label-tertiary: rgba(235, 235, 245, 0.3);
    --color-bg: #000000;
    --color-bg-secondary: #1C1C1E;
    --color-separator: rgba(84, 84, 88, 0.6);
    --glass-bg: rgba(30, 30, 30, 0.6);
    --glass-border: rgba(255, 255, 255, 0.08);
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

*Authoritative sources to keep handy: Apple Human Interface Guidelines (developer.apple.com/design/human-interface-guidelines), the WWDC 2025 sessions "Meet Liquid Glass" and "Get to know the new design system," SF Symbols app, and Apple Design Resources.*