/** The Design Studio's manual image pipeline — a dependency-free canvas renderer.
 *
 *  The Designer's manual edits (crop, straighten, tune, sharpen, vignette) are
 *  applied here in the browser rather than server-side: a slider has to repaint at
 *  interactive speed, and a round-trip per tick would make the studio unusable.
 *  The flattened result is uploaded once, on save, and lands as a new version in
 *  the hero image's version thread — same as an AI edit or a custom upload.
 *
 *  Everything below is pure: `renderEdit` takes a decoded image plus an `EditOps`
 *  and returns a fresh canvas, so the preview and the full-resolution save run the
 *  exact same code at different resolutions.
 */

/** A normalized crop rectangle, in the *straightened* frame (0..1 on each axis). */
export interface CropRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** One control point on a tone curve, both axes 0..255 (input → output). */
export type CurvePoint = [number, number];

/** The tone curves: a composite applied to all channels, plus per-channel ones.
 *  Each is a sorted point list; the identity is exactly [[0,0],[255,255]]. */
export interface Curves {
  rgb: CurvePoint[];
  r: CurvePoint[];
  g: CurvePoint[];
  b: CurvePoint[];
}

export type CurveChannel = keyof Curves;

/** Hue / saturation / luminance offsets for one colour band (each −100..100). */
export interface HslShift {
  h: number;
  s: number;
  l: number;
}

/** The eight colour bands, keyed by name. `orange` is the skin-tone band. */
export type HslBands = Record<HslBandKey, HslShift>;
export type HslBandKey =
  | 'red'
  | 'orange'
  | 'yellow'
  | 'green'
  | 'aqua'
  | 'blue'
  | 'purple'
  | 'magenta';

/** Band centres in degrees, in hue order — the same eight a raw developer uses.
 *  Every pixel is split between its two neighbouring bands, so the weights always
 *  sum to 1 and no hue falls into a gap. */
export const HSL_BANDS: { key: HslBandKey; label: string; hue: number; hint?: string }[] = [
  { key: 'red', label: 'Red', hue: 0 },
  { key: 'orange', label: 'Orange', hue: 30, hint: 'Skin tones' },
  { key: 'yellow', label: 'Yellow', hue: 60 },
  { key: 'green', label: 'Green', hue: 120 },
  { key: 'aqua', label: 'Aqua', hue: 180 },
  { key: 'blue', label: 'Blue', hue: 240 },
  { key: 'purple', label: 'Purple', hue: 280 },
  { key: 'magenta', label: 'Magenta', hue: 320 },
];

/** Tonal adjustments. Every value is −100..100 (0 = untouched) except `sharpen`,
 *  `vignette` and `grain`, which are 0..100. */
export interface Adjustments {
  brightness: number;
  contrast: number;
  saturation: number;
  warmth: number; // blue ↔ amber
  tint: number; // green ↔ magenta
  highlights: number; // recover (−) or lift (+) the bright end
  shadows: number; // deepen (−) or open up (+) the dark end
  vibrance: number; // saturation weighted toward already-muted pixels
  sharpen: number; // fine-radius unsharp mask
  structure: number; // wide-radius unsharp mask (clarity); negative softens
  vignette: number;
  grain: number;
}

/** The full, serializable description of one manual edit. */
export interface EditOps {
  crop: CropRect;
  /** The crop aspect the Designer locked, kept so the UI can restore the choice. */
  aspect: string | null;
  rotate: 0 | 90 | 180 | 270;
  flipH: boolean;
  flipV: boolean;
  straighten: number; // −45..45 degrees
  adj: Adjustments;
  curves: Curves;
  hsl: HslBands;
}

export const FULL_CROP: CropRect = { x: 0, y: 0, w: 1, h: 1 };

export const IDENTITY_CURVE: CurvePoint[] = [
  [0, 0],
  [255, 255],
];

export const IDENTITY_CURVES: Curves = {
  rgb: IDENTITY_CURVE,
  r: IDENTITY_CURVE,
  g: IDENTITY_CURVE,
  b: IDENTITY_CURVE,
};

export const NEUTRAL_HSL: HslBands = Object.fromEntries(
  HSL_BANDS.map((b) => [b.key, { h: 0, s: 0, l: 0 }]),
) as HslBands;

export const NEUTRAL_ADJUSTMENTS: Adjustments = {
  brightness: 0,
  contrast: 0,
  saturation: 0,
  warmth: 0,
  tint: 0,
  highlights: 0,
  shadows: 0,
  vibrance: 0,
  sharpen: 0,
  structure: 0,
  vignette: 0,
  grain: 0,
};

export const DEFAULT_OPS: EditOps = {
  crop: FULL_CROP,
  aspect: null,
  rotate: 0,
  flipH: false,
  flipV: false,
  straighten: 0,
  adj: NEUTRAL_ADJUSTMENTS,
  curves: IDENTITY_CURVES,
  hsl: NEUTRAL_HSL,
};

/** Crop aspect presets — "Original" and free-form plus the ad shapes the banner
 *  templates output (square hero, story/portrait, landscape, wide link unit). */
export const ASPECT_PRESETS: { key: string; label: string; ratio: number | null }[] = [
  { key: 'free', label: 'Free', ratio: null },
  { key: 'original', label: 'Original', ratio: 0 }, // 0 = the source's own ratio
  { key: '1:1', label: '1:1', ratio: 1 },
  { key: '4:5', label: '4:5', ratio: 4 / 5 },
  { key: '3:4', label: '3:4', ratio: 3 / 4 },
  { key: '2:3', label: '2:3', ratio: 2 / 3 },
  { key: '16:9', label: '16:9', ratio: 16 / 9 },
  { key: '9:16', label: '9:16', ratio: 9 / 16 },
  { key: '21:9', label: '21:9', ratio: 21 / 9 },
];

export type Source = HTMLImageElement | HTMLCanvasElement;

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);
const clamp01 = (v: number) => clamp(v, 0, 1);
const rad = (deg: number) => (deg * Math.PI) / 180;

export function sourceSize(src: Source): { w: number; h: number } {
  return src instanceof HTMLCanvasElement
    ? { w: src.width, h: src.height }
    : { w: src.naturalWidth, h: src.naturalHeight };
}

/** True when a curve has been left alone (exactly the two end points). */
export function isIdentityCurve(points: CurvePoint[]): boolean {
  return (
    points.length === 2 &&
    points[0][0] === 0 &&
    points[0][1] === 0 &&
    points[1][0] === 255 &&
    points[1][1] === 255
  );
}

export function curvesTouched(curves: Curves): boolean {
  return (Object.keys(curves) as CurveChannel[]).some((c) => !isIdentityCurve(curves[c]));
}

export function hslTouched(hsl: HslBands): boolean {
  return HSL_BANDS.some((b) => hsl[b.key].h !== 0 || hsl[b.key].s !== 0 || hsl[b.key].l !== 0);
}

/** True when nothing has been changed — used to skip work and to disable Save. */
export function isNeutral(ops: EditOps): boolean {
  const { crop, adj } = ops;
  const untouchedCrop = crop.x === 0 && crop.y === 0 && crop.w === 1 && crop.h === 1;
  const untouchedGeometry =
    untouchedCrop && ops.rotate === 0 && !ops.flipH && !ops.flipV && ops.straighten === 0;
  return (
    untouchedGeometry &&
    (Object.keys(adj) as (keyof Adjustments)[]).every((k) => adj[k] === 0) &&
    !curvesTouched(ops.curves) &&
    !hslTouched(ops.hsl)
  );
}

/** Expand a curve's control points into a 256-entry lookup table.
 *
 *  Interpolation is monotone cubic (Fritsch–Carlson tangent limiting) rather than a
 *  plain spline: an ordinary Catmull-Rom overshoots between close control points,
 *  which shows up as banding and inverted contrast in the shadows.
 */
export function buildCurveLut(points: CurvePoint[]): Uint8ClampedArray {
  const lut = new Uint8ClampedArray(256);
  const pts = [...points].sort((a, b) => a[0] - b[0]);
  if (pts.length === 0) {
    for (let i = 0; i < 256; i++) lut[i] = i;
    return lut;
  }
  if (pts.length === 1) {
    lut.fill(clamp(pts[0][1], 0, 255));
    return lut;
  }

  const n = pts.length;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);

  // Secant slopes, then Fritsch–Carlson-limited tangents.
  const slope: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    const dx = xs[i + 1] - xs[i];
    slope.push(dx === 0 ? 0 : (ys[i + 1] - ys[i]) / dx);
  }
  const tangent: number[] = new Array(n);
  tangent[0] = slope[0];
  tangent[n - 1] = slope[n - 2];
  for (let i = 1; i < n - 1; i++) {
    if (slope[i - 1] * slope[i] <= 0) tangent[i] = 0;
    else tangent[i] = (slope[i - 1] + slope[i]) / 2;
  }
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      tangent[i] = 0;
      tangent[i + 1] = 0;
      continue;
    }
    const a = tangent[i] / slope[i];
    const b = tangent[i + 1] / slope[i];
    const s = a * a + b * b;
    if (s > 9) {
      const t = 3 / Math.sqrt(s);
      tangent[i] = t * a * slope[i];
      tangent[i + 1] = t * b * slope[i];
    }
  }

  let seg = 0;
  for (let x = 0; x < 256; x++) {
    if (x <= xs[0]) {
      lut[x] = ys[0];
      continue;
    }
    if (x >= xs[n - 1]) {
      lut[x] = ys[n - 1];
      continue;
    }
    while (seg < n - 2 && x > xs[seg + 1]) seg++;
    const h = xs[seg + 1] - xs[seg];
    if (h === 0) {
      lut[x] = ys[seg + 1];
      continue;
    }
    const t = (x - xs[seg]) / h;
    const t2 = t * t;
    const t3 = t2 * t;
    // Hermite basis.
    lut[x] =
      (2 * t3 - 3 * t2 + 1) * ys[seg] +
      (t3 - 2 * t2 + t) * h * tangent[seg] +
      (-2 * t3 + 3 * t2) * ys[seg + 1] +
      (t3 - t2) * h * tangent[seg + 1];
  }
  return lut;
}

/** Frame size after the 90° steps (flips don't change the shape). */
export function orientedSize(src: Source, ops: EditOps): { w: number; h: number } {
  const { w, h } = sourceSize(src);
  return ops.rotate === 90 || ops.rotate === 270 ? { w: h, h: w } : { w, h };
}

/** The pixel size a render of `ops` produces, before any `maxEdge` downscale. */
export function croppedSize(src: Source, ops: EditOps): { w: number; h: number } {
  const frame = orientedSize(src, ops);
  return {
    w: Math.max(1, Math.round(frame.w * ops.crop.w)),
    h: Math.max(1, Math.round(frame.h * ops.crop.h)),
  };
}

function makeCanvas(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}

function context(c: HTMLCanvasElement): CanvasRenderingContext2D {
  const ctx = c.getContext('2d', { willReadFrequently: true });
  if (!ctx) throw new Error('Canvas 2D is unavailable in this browser');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  return ctx;
}

/** How far a w×h frame must be scaled up so that, rotated by `angle`, it still
 *  covers the original frame — this is what keeps empty corners out of a
 *  straighten (the same trick Snapseed's straighten uses). */
function coverScale(w: number, h: number, angle: number): number {
  const c = Math.abs(Math.cos(angle));
  const s = Math.abs(Math.sin(angle));
  return Math.max((w * c + h * s) / w, (w * s + h * c) / h);
}

/** The CSS-filter part of the tone stage. brightness/contrast/saturation are
 *  native (fast, correctly gamma-handled), so they never enter the pixel loop. */
function filterString(adj: Adjustments): string {
  const parts: string[] = [];
  if (adj.brightness) parts.push(`brightness(${(1 + (adj.brightness / 100) * 0.6).toFixed(4)})`);
  if (adj.contrast) parts.push(`contrast(${(1 + (adj.contrast / 100) * 0.7).toFixed(4)})`);
  if (adj.saturation) parts.push(`saturate(${(1 + adj.saturation / 100).toFixed(4)})`);
  return parts.length ? parts.join(' ') : 'none';
}

/** A blurred copy of `src`, used as the low-frequency reference for an unsharp mask. */
function blurred(src: HTMLCanvasElement, radius: number): Uint8ClampedArray {
  const c = makeCanvas(src.width, src.height);
  const ctx = context(c);
  ctx.filter = `blur(${radius}px)`;
  ctx.drawImage(src, 0, 0);
  return ctx.getImageData(0, 0, c.width, c.height).data;
}

/** Deterministic per-pixel noise in 0..1 — a hash rather than Math.random, so a
 *  re-render of identical ops produces an identical grain instead of shimmering. */
function noiseAt(i: number): number {
  let x = (i * 2654435761) >>> 0;
  x ^= x >>> 15;
  x = (x * 2246822519) >>> 0;
  x ^= x >>> 13;
  return x / 4294967296;
}

/** The single-pass pixel stage: unsharp deltas, tone curves, colour temperature,
 *  per-band HSL, tonal masks, vibrance, vignette and grain — one read, one write.
 *
 *  Order matters and mirrors a raw developer: detail first (its blur references
 *  were taken from this canvas, so they have to be applied against the same
 *  values), then the tone curve, then colour, then the tonal masks, then the
 *  optical effects. Every block is gated, so an untouched control costs nothing.
 */
function applyPixelStage(canvas: HTMLCanvasElement, adj: Adjustments, curves: Curves, hsl: HslBands): void {
  const wantsSharpen = adj.sharpen !== 0;
  const wantsStructure = adj.structure !== 0;
  const wantsColour = adj.warmth !== 0 || adj.tint !== 0;
  const wantsTone = adj.highlights !== 0 || adj.shadows !== 0 || adj.vibrance !== 0;
  const wantsVignette = adj.vignette !== 0;
  const wantsGrain = adj.grain !== 0;
  const wantsCurves = curvesTouched(curves);
  const wantsHsl = hslTouched(hsl);
  if (
    !wantsSharpen &&
    !wantsStructure &&
    !wantsColour &&
    !wantsTone &&
    !wantsVignette &&
    !wantsGrain &&
    !wantsCurves &&
    !wantsHsl
  )
    return;

  const { width: w, height: h } = canvas;
  const ctx = context(canvas);
  const image = ctx.getImageData(0, 0, w, h);
  const d = image.data;

  // Unsharp references. Radii are in CSS pixels: ~1px isolates edge detail
  // (sharpen), ~8px isolates local contrast (structure / clarity).
  const fine = wantsSharpen ? blurred(canvas, Math.max(0.6, w / 1200 + 0.8)) : null;
  const wide = wantsStructure ? blurred(canvas, Math.max(4, w / 160)) : null;
  const sharpenAmount = (adj.sharpen / 100) * 1.1;
  const structureAmount = (adj.structure / 100) * 0.7;

  const warmth = (adj.warmth / 100) * 34;
  const tint = (adj.tint / 100) * 26;
  const highlights = (adj.highlights / 100) * 0.75;
  const shadows = (adj.shadows / 100) * 0.95;
  const vibrance = adj.vibrance / 100;
  const vignette = adj.vignette / 100;
  const grain = (adj.grain / 100) * 26;

  // Tone curves, expanded once into lookup tables.
  const lutRgb = wantsCurves ? buildCurveLut(curves.rgb) : null;
  const lutR = wantsCurves ? buildCurveLut(curves.r) : null;
  const lutG = wantsCurves ? buildCurveLut(curves.g) : null;
  const lutB = wantsCurves ? buildCurveLut(curves.b) : null;

  // HSL bands, flattened into parallel arrays in hue order so the per-pixel path
  // is two array reads rather than an object lookup.
  const bandHue = HSL_BANDS.map((band) => band.hue);
  const bandH = HSL_BANDS.map((band) => hsl[band.key].h);
  const bandS = HSL_BANDS.map((band) => hsl[band.key].s);
  const bandL = HSL_BANDS.map((band) => hsl[band.key].l);
  const bandTouched = HSL_BANDS.map(
    (band) => hsl[band.key].h !== 0 || hsl[band.key].s !== 0 || hsl[band.key].l !== 0,
  );
  const bandCount = bandHue.length;

  // Vignette geometry — normalized radius from the frame centre.
  const cx = w / 2;
  const cy = h / 2;
  const maxDist = Math.hypot(cx, cy) || 1;

  for (let i = 0, p = 0; i < d.length; i += 4, p++) {
    let r = d[i];
    let g = d[i + 1];
    let b = d[i + 2];

    if (fine) {
      r += sharpenAmount * (r - fine[i]);
      g += sharpenAmount * (g - fine[i + 1]);
      b += sharpenAmount * (b - fine[i + 2]);
    }
    if (wide) {
      r += structureAmount * (r - wide[i]);
      g += structureAmount * (g - wide[i + 1]);
      b += structureAmount * (b - wide[i + 2]);
    }

    if (lutRgb && lutR && lutG && lutB) {
      // LUTs are indexed, so the running floats have to be clamped to bytes first.
      r = lutRgb[lutR[r < 0 ? 0 : r > 255 ? 255 : r | 0]];
      g = lutRgb[lutG[g < 0 ? 0 : g > 255 ? 255 : g | 0]];
      b = lutRgb[lutB[b < 0 ? 0 : b > 255 ? 255 : b | 0]];
    }

    if (wantsColour) {
      r += warmth + tint * 0.5;
      g -= tint;
      b += -warmth + tint * 0.5;
    }

    if (wantsHsl) {
      const mx = r > g ? (r > b ? r : b) : g > b ? g : b;
      const mn = r < g ? (r < b ? r : b) : g < b ? g : b;
      const chroma = mx - mn;
      // A near-neutral pixel has no meaningful hue — leaving it alone is what keeps
      // a grey wall from picking up a colour cast when a band is pushed.
      if (chroma > 2) {
        let hue: number;
        if (mx === r) hue = ((g - b) / chroma) * 60;
        else if (mx === g) hue = ((b - r) / chroma + 2) * 60;
        else hue = ((r - g) / chroma + 4) * 60;
        if (hue < 0) hue += 360;

        // Split the pixel between its two neighbouring bands (weights sum to 1).
        let lo = bandCount - 1;
        for (let k = 0; k < bandCount; k++) {
          if (bandHue[k] <= hue) lo = k;
          else break;
        }
        const hi = (lo + 1) % bandCount;
        let span = bandHue[hi] - bandHue[lo];
        if (span <= 0) span += 360;
        let t = (hue - bandHue[lo]) / span;
        if (t > 1) t = 1;
        const wLo = 1 - t;

        // Skip the rebuild entirely unless one of the two contributing bands was
        // actually touched — an image graded on one band only pays for that band.
        if (bandTouched[lo] || bandTouched[hi]) {
          // Fade in with chroma so pastels shift less than fully saturated hues.
          const strength = chroma > 40 ? 1 : chroma / 40;
          const dHue = (bandH[lo] * wLo + bandH[hi] * t) * 0.3 * strength; // ±30°
          const satMul = 1 + ((bandS[lo] * wLo + bandS[hi] * t) / 100) * strength;
          const lumMul = 1 + ((bandL[lo] * wLo + bandL[hi] * t) / 100) * 0.7 * strength;
          // Rebuild the pixel from the shifted hue, keeping the HSL relationship.
          const l = (mx + mn) / 2;
          const sat = l > 127.5 ? chroma / (510 - mx - mn) : chroma / (mx + mn || 1);
          let h2 = hue + dHue;
          if (h2 < 0) h2 += 360;
          if (h2 >= 360) h2 -= 360;
          const s2 = clamp(sat * satMul, 0, 1);
          const l2 = clamp((l / 255) * lumMul, 0, 1);
          const c = (1 - Math.abs(2 * l2 - 1)) * s2;
          const hp = h2 / 60;
          const xx = c * (1 - Math.abs((hp % 2) - 1));
          let r2 = 0;
          let g2 = 0;
          let b2 = 0;
          if (hp < 1) {
            r2 = c;
            g2 = xx;
          } else if (hp < 2) {
            r2 = xx;
            g2 = c;
          } else if (hp < 3) {
            g2 = c;
            b2 = xx;
          } else if (hp < 4) {
            g2 = xx;
            b2 = c;
          } else if (hp < 5) {
            r2 = xx;
            b2 = c;
          } else {
            r2 = c;
            b2 = xx;
          }
          const m = l2 - c / 2;
          r = (r2 + m) * 255;
          g = (g2 + m) * 255;
          b = (b2 + m) * 255;
        }
      }
    }

    if (wantsTone) {
      const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
      if (highlights) {
        // Weighted to the bright end, so recovery leaves midtones alone.
        const f = 1 + highlights * lum * lum;
        r *= f;
        g *= f;
        b *= f;
      }
      if (shadows) {
        const dark = 1 - lum;
        const f = 1 + shadows * dark * dark;
        r *= f;
        g *= f;
        b *= f;
      }
      if (vibrance) {
        const mx = Math.max(r, g, b);
        const mn = Math.min(r, g, b);
        // Push already-muted pixels harder than saturated ones.
        const boost = vibrance * (1 - (mx - mn) / 255);
        const grey = 0.299 * r + 0.587 * g + 0.114 * b;
        r = grey + (r - grey) * (1 + boost);
        g = grey + (g - grey) * (1 + boost);
        b = grey + (b - grey) * (1 + boost);
      }
    }

    if (wantsVignette) {
      const x = p % w;
      const y = (p - x) / w;
      const dist = Math.hypot(x - cx, y - cy) / maxDist;
      const f = 1 - vignette * Math.pow(dist, 2.2);
      r *= f;
      g *= f;
      b *= f;
    }

    if (wantsGrain) {
      const n = (noiseAt(p) - 0.5) * grain;
      r += n;
      g += n;
      b += n;
    }

    d[i] = r < 0 ? 0 : r > 255 ? 255 : r;
    d[i + 1] = g < 0 ? 0 : g > 255 ? 255 : g;
    d[i + 2] = b < 0 ? 0 : b > 255 ? 255 : b;
  }

  ctx.putImageData(image, 0, 0);
}

/** Render `ops` over `src` and return a new canvas.
 *
 *  Stages, in order: orient (90° steps + flips) → straighten (rotate and scale to
 *  cover) → crop → tone. `maxEdge` caps the long edge, which is how the live
 *  preview stays interactive while the save runs the identical pipeline at full
 *  resolution. `ignoreCrop` renders the whole straightened frame — the crop tool
 *  needs to show what's being cut away.
 */
export function renderEdit(
  src: Source,
  ops: EditOps,
  opts: { maxEdge?: number; ignoreCrop?: boolean } = {},
): HTMLCanvasElement {
  const { w: sw, h: sh } = sourceSize(src);
  if (!sw || !sh) throw new Error('Source image has no dimensions');

  // ── Orient: 90° steps and flips ───────────────────────────────────────────
  const swap = ops.rotate === 90 || ops.rotate === 270;
  const fw = swap ? sh : sw;
  const fh = swap ? sw : sh;
  let frame = makeCanvas(fw, fh);
  {
    const ctx = context(frame);
    ctx.translate(fw / 2, fh / 2);
    ctx.rotate(rad(ops.rotate));
    ctx.scale(ops.flipH ? -1 : 1, ops.flipV ? -1 : 1);
    ctx.drawImage(src, -sw / 2, -sh / 2, sw, sh);
  }

  // ── Straighten: rotate in place, scaled up so no corner falls empty ───────
  if (ops.straighten) {
    const angle = rad(ops.straighten);
    const scale = coverScale(fw, fh, angle);
    const next = makeCanvas(fw, fh);
    const ctx = context(next);
    ctx.translate(fw / 2, fh / 2);
    ctx.rotate(angle);
    ctx.scale(scale, scale);
    ctx.drawImage(frame, -fw / 2, -fh / 2, fw, fh);
    frame = next;
  }

  // ── Crop + downscale ─────────────────────────────────────────────────────
  const crop = opts.ignoreCrop ? FULL_CROP : ops.crop;
  const sx = clamp(crop.x, 0, 1) * fw;
  const sy = clamp(crop.y, 0, 1) * fh;
  const cw = Math.max(1, clamp(crop.w, 0, 1) * fw);
  const ch = Math.max(1, clamp(crop.h, 0, 1) * fh);

  let outW = cw;
  let outH = ch;
  const maxEdge = opts.maxEdge;
  if (maxEdge && Math.max(cw, ch) > maxEdge) {
    const k = maxEdge / Math.max(cw, ch);
    outW = cw * k;
    outH = ch * k;
  }

  const out = makeCanvas(outW, outH);
  const ctx = context(out);
  ctx.filter = filterString(ops.adj);
  ctx.drawImage(frame, sx, sy, cw, ch, 0, 0, out.width, out.height);
  ctx.filter = 'none';

  // ── Tone: the single pixel pass ──────────────────────────────────────────
  applyPixelStage(out, ops.adj, ops.curves, ops.hsl);
  return out;
}

/** Per-channel and luma distributions plus the clipped-pixel counts, read off a
 *  rendered canvas. Drives the histogram panel and the clipping readout. */
export interface Histogram {
  luma: Uint32Array;
  r: Uint32Array;
  g: Uint32Array;
  b: Uint32Array;
  total: number;
  clippedHigh: number; // pixels with a channel at/near 255 — blown
  clippedLow: number; // pixels with a channel at/near 0 — crushed
}

export function histogramOf(canvas: HTMLCanvasElement): Histogram {
  const { width: w, height: h } = canvas;
  const d = context(canvas).getImageData(0, 0, w, h).data;
  const luma = new Uint32Array(256);
  const r = new Uint32Array(256);
  const g = new Uint32Array(256);
  const b = new Uint32Array(256);
  let clippedHigh = 0;
  let clippedLow = 0;
  for (let i = 0; i < d.length; i += 4) {
    const rr = d[i];
    const gg = d[i + 1];
    const bb = d[i + 2];
    r[rr]++;
    g[gg]++;
    b[bb]++;
    luma[(0.299 * rr + 0.587 * gg + 0.114 * bb) | 0]++;
    if (rr >= CLIP_HIGH || gg >= CLIP_HIGH || bb >= CLIP_HIGH) clippedHigh++;
    else if (rr <= CLIP_LOW && gg <= CLIP_LOW && bb <= CLIP_LOW) clippedLow++;
  }
  return { luma, r, g, b, total: (d.length / 4) | 0, clippedHigh, clippedLow };
}

const CLIP_HIGH = 254;
const CLIP_LOW = 1;

/** Paint clipping warnings onto a *preview* canvas: blown highlights red, crushed
 *  shadows blue. Destructive, so only ever call this on the on-screen copy — never
 *  on the canvas that gets encoded and saved. */
export function markClipping(canvas: HTMLCanvasElement): void {
  const ctx = context(canvas);
  const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const d = image.data;
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i];
    const g = d[i + 1];
    const b = d[i + 2];
    if (r >= CLIP_HIGH || g >= CLIP_HIGH || b >= CLIP_HIGH) {
      d[i] = 255;
      d[i + 1] = 32;
      d[i + 2] = 32;
    } else if (r <= CLIP_LOW && g <= CLIP_LOW && b <= CLIP_LOW) {
      d[i] = 40;
      d[i + 1] = 120;
      d[i + 2] = 255;
    }
  }
  ctx.putImageData(image, 0, 0);
}

/** Solve Warmth/Tint so the sampled pixel becomes neutral grey.
 *
 *  The pixel stage applies `r += W + T/2 ; g -= T ; b += −W + T/2` where
 *  W = warmth/100·34 and T = tint/100·26. Setting r' = g' = b' gives
 *  W = (b−r)/2 and T = (g − (r+b)/2)/1.5 — so one click on something that should
 *  be neutral lands both sliders, instead of hunting for the cast by eye.
 *  The sample must come from a render with Warmth and Tint at zero.
 */
export function neutralizeFrom(r: number, g: number, b: number): { warmth: number; tint: number } {
  const W = (b - r) / 2;
  const T = (g - (r + b) / 2) / 1.5;
  return {
    warmth: Math.round(clamp(W / 0.34, -100, 100)),
    tint: Math.round(clamp(T / 0.26, -100, 100)),
  };
}

/** Human-readable labels for the tune/detail sliders, used by the UI and by
 *  `describeOps` so the version-history line reads the same as the panel. */
export const ADJUSTMENT_LABELS: Record<keyof Adjustments, string> = {
  brightness: 'Brightness',
  contrast: 'Contrast',
  saturation: 'Saturation',
  warmth: 'Warmth',
  tint: 'Tint',
  highlights: 'Highlights',
  shadows: 'Shadows',
  vibrance: 'Vibrance',
  sharpen: 'Sharpen',
  structure: 'Structure',
  vignette: 'Vignette',
  grain: 'Grain',
};

/** A one-line summary of what was changed — stored as the version's comment, so
 *  the history reads "Manual edit · Crop 4:5 · Straighten −1.5° · Warmth +12". */
export function describeOps(ops: EditOps): string {
  const parts: string[] = [];
  const { crop } = ops;
  if (crop.x !== 0 || crop.y !== 0 || crop.w !== 1 || crop.h !== 1) {
    const preset = ops.aspect && ops.aspect !== 'free' ? ` ${ops.aspect}` : '';
    parts.push(`Crop${preset} ${Math.round(crop.w * 100)}%×${Math.round(crop.h * 100)}%`);
  }
  if (ops.rotate) parts.push(`Rotate ${ops.rotate}°`);
  if (ops.flipH) parts.push('Flip H');
  if (ops.flipV) parts.push('Flip V');
  if (ops.straighten) parts.push(`Straighten ${signed(ops.straighten, 1)}°`);
  for (const key of Object.keys(ADJUSTMENT_LABELS) as (keyof Adjustments)[]) {
    const v = ops.adj[key];
    if (v) parts.push(`${ADJUSTMENT_LABELS[key]} ${signed(v, 0)}`);
  }
  // Curves and HSL are multi-valued, so name the channels/bands touched rather
  // than every number — the history line has to stay one readable sentence.
  const channels = (Object.keys(ops.curves) as CurveChannel[]).filter(
    (c) => !isIdentityCurve(ops.curves[c]),
  );
  if (channels.length) {
    parts.push(`Curves ${channels.map((c) => (c === 'rgb' ? 'RGB' : c.toUpperCase())).join('/')}`);
  }
  const bands = HSL_BANDS.filter(
    (b) => ops.hsl[b.key].h !== 0 || ops.hsl[b.key].s !== 0 || ops.hsl[b.key].l !== 0,
  );
  if (bands.length) parts.push(`HSL ${bands.map((b) => b.label).join('/')}`);
  return parts.length ? `Manual edit · ${parts.join(' · ')}` : 'Manual edit';
}

function signed(v: number, digits: number): string {
  const s = v.toFixed(digits);
  // Use a real minus sign so the summary matches the slider readouts.
  return v > 0 ? `+${s}` : s.replace('-', '−');
}

/** Encode a rendered canvas for upload.
 *
 *  PNG keeps the hero lossless, but a 4K render can blow past the server's 10 MB
 *  per-image ceiling — so fall back to high-quality JPEG rather than failing the
 *  save. Returns the blob and its MIME type.
 */
export async function encodeCanvas(
  canvas: HTMLCanvasElement,
  maxBytes: number,
): Promise<{ blob: Blob; type: string }> {
  const png = await toBlob(canvas, 'image/png');
  if (png.size <= maxBytes) return { blob: png, type: 'image/png' };
  for (const quality of [0.94, 0.88, 0.8]) {
    const jpeg = await toBlob(canvas, 'image/jpeg', quality);
    if (jpeg.size <= maxBytes) return { blob: jpeg, type: 'image/jpeg' };
  }
  throw new Error('Edited image is too large to save — crop it smaller and try again.');
}

function toBlob(canvas: HTMLCanvasElement, type: string, quality?: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('Could not encode the edited image'))),
      type,
      quality,
    );
  });
}

/** Load an object URL into a decoded image the renderer can draw. */
export function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Could not load the image'));
    img.src = url;
  });
}

/** Fit a crop rect to `ratio` (w/h) inside a `frameRatio` frame, centred and as
 *  large as it will go — what the aspect presets snap to. */
export function cropForAspect(ratio: number, frameRatio: number): CropRect {
  // Work in normalized space: a rect of normalized w,h has pixel ratio
  // (w * frameW) / (h * frameH) = (w / h) * frameRatio.
  let w = 1;
  let h = 1;
  if (ratio >= frameRatio) h = frameRatio / ratio;
  else w = ratio / frameRatio;
  return { x: (1 - w) / 2, y: (1 - h) / 2, w, h };
}

/** Keep a crop rect inside the frame, above a minimum size, and (when locked) on
 *  its aspect — the invariant every drag handler funnels through. */
export function normalizeCrop(rect: CropRect, ratio: number | null, frameRatio: number): CropRect {
  const MIN = 0.06;
  let w = clamp(rect.w, MIN, 1);
  let h = clamp(rect.h, MIN, 1);
  if (ratio) {
    // Honour the ratio on the axis that still fits.
    const target = ratio / frameRatio; // normalized w/h
    if (w / h > target) w = h * target;
    else h = w / target;
    if (w > 1) {
      w = 1;
      h = w / target;
    }
    if (h > 1) {
      h = 1;
      w = h * target;
    }
  }
  const x = clamp01(clamp(rect.x, 0, 1 - w));
  const y = clamp01(clamp(rect.y, 0, 1 - h));
  return { x, y, w, h };
}
