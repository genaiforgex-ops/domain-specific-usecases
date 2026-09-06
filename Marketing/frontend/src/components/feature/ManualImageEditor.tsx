import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Crop as CropIcon,
  Droplets,
  Eye,
  FlipHorizontal2,
  FlipVertical2,
  LayoutTemplate,
  Maximize2,
  Palette,
  Pipette,
  RotateCcw,
  RotateCw,
  Redo2,
  RefreshCw,
  Sliders,
  Sparkles,
  SunMedium,
  TrendingUp,
  Undo2,
  Wand2,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { Button } from '../ui/Button';
import { Pill } from '../ui/primitives';
import { AD_SIZE_LABELS } from '../../lib/adSizes';
import { api, ApiError } from '../../lib/api';
import { cn } from '../../lib/cn';
import {
  ADJUSTMENT_LABELS,
  ASPECT_PRESETS,
  DEFAULT_OPS,
  FULL_CROP,
  HSL_BANDS,
  IDENTITY_CURVE,
  IDENTITY_CURVES,
  NEUTRAL_HSL,
  buildCurveLut,
  croppedSize,
  cropForAspect,
  curvesTouched,
  describeOps,
  encodeCanvas,
  histogramOf,
  hslTouched,
  isIdentityCurve,
  isNeutral,
  loadImage,
  markClipping,
  neutralizeFrom,
  normalizeCrop,
  orientedSize,
  renderEdit,
  sourceSize,
  type Adjustments,
  type CropRect,
  type CurveChannel,
  type CurvePoint,
  type Curves,
  type EditOps,
  type Histogram,
  type HslBandKey,
} from '../../lib/imageEdit';
import type { BannerImage, HeroGuides } from '../../lib/types';

// The server keeps a hard 10 MB ceiling per image version; stay under it with a
// little headroom so a save never round-trips just to be rejected.
const MAX_SAVE_BYTES = 9_500_000;
// Preview resolution caps. The idle cap is big enough to judge sharpness on a 4K
// display; while a slider or handle is actually being dragged the preview drops to
// the interactive cap so the pixel stage (curves, HSL, unsharp) still repaints
// inside a frame. Zooming in raises the cap so a 1:1 inspection is real pixels.
const PREVIEW_MAX_EDGE = 1800;
const PREVIEW_MAX_EDGE_ZOOMED = 2800;
const PREVIEW_INTERACTIVE_EDGE = 900;
const MAX_ZOOM = 8;

type ToolKey = 'crop' | 'rotate' | 'tune' | 'curves' | 'colour' | 'details' | 'effects';

const TOOLS: { key: ToolKey; label: string; icon: typeof CropIcon }[] = [
  { key: 'crop', label: 'Crop', icon: CropIcon },
  { key: 'rotate', label: 'Rotate', icon: RotateCw },
  { key: 'tune', label: 'Tune', icon: SunMedium },
  { key: 'curves', label: 'Curves', icon: TrendingUp },
  { key: 'colour', label: 'Colour', icon: Palette },
  { key: 'details', label: 'Details', icon: Sliders },
  { key: 'effects', label: 'Effects', icon: Droplets },
];

const CURVE_CHANNELS: { key: CurveChannel; label: string; stroke: string }[] = [
  { key: 'rgb', label: 'RGB', stroke: 'currentColor' },
  { key: 'r', label: 'Red', stroke: '#e5484d' },
  { key: 'g', label: 'Green', stroke: '#30a46c' },
  { key: 'b', label: 'Blue', stroke: '#0091ff' },
];

const TUNE_KEYS: (keyof Adjustments)[] = [
  'brightness',
  'contrast',
  'saturation',
  'warmth',
  'tint',
  'highlights',
  'shadows',
  'vibrance',
];
const DETAIL_KEYS: (keyof Adjustments)[] = ['sharpen', 'structure'];
const EFFECT_KEYS: (keyof Adjustments)[] = ['vignette', 'grain'];

// Sliders that only make sense one-way (there is no negative sharpening here).
const ONE_WAY: ReadonlySet<keyof Adjustments> = new Set(['sharpen', 'vignette', 'grain']);

const clampNum = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

/** The Design Studio's manual editor — the hand-tools half of hero-image editing.
 *
 *  The Designer gets the toolset they'd expect from Snapseed or Lightroom: crop
 *  with ad-shape presets, 90° rotation, flips, fine straightening, the tone
 *  sliders, sharpen/structure and vignette/grain. Everything renders in the
 *  browser (see lib/imageEdit) so sliders are immediate; on save the pipeline is
 *  re-run at full resolution and the flattened PNG is appended to the image's
 *  version thread, exactly like an AI edit — so it stays revertible and feeds the
 *  approval gate and the Figma export unchanged.
 */
export function ManualImageEditor({
  briefId,
  image,
  headline,
  guides,
  onClose,
  onUpdated,
  onSwitchToAi,
}: Readonly<{
  briefId: string;
  image: BannerImage | null;
  headline: string;
  /** How the chosen banner template crops this hero — drives the crop guides. */
  guides?: HeroGuides | null;
  onClose: () => void;
  onUpdated: (img: BannerImage) => void;
  /** Hand this image over to the conversational editor instead. */
  onSwitchToAi?: () => void;
}>) {
  const imageId = image?.id ?? null;
  const open = imageId !== null;

  const [source, setSource] = useState<HTMLImageElement | null>(null);
  const [ops, setOps] = useState<EditOps>(DEFAULT_OPS);
  const [undoStack, setUndoStack] = useState<EditOps[]>([]);
  const [redoStack, setRedoStack] = useState<EditOps[]>([]);
  const [tool, setTool] = useState<ToolKey>('crop');
  const [compare, setCompare] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Inspection state: zoom/pan over the preview, the histogram read off the last
  // render, and the clipping overlay toggle.
  const [zoom, setZoom] = useState(1); // 1 = fit to the stage
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [histogram, setHistogram] = useState<Histogram | null>(null);
  const [showClipping, setShowClipping] = useState(false);
  // Dragging drops the preview resolution; this tracks when a gesture is live.
  const [interacting, setInteracting] = useState(false);
  // Which template crop guides to draw over the crop frame.
  const [guideMode, setGuideMode] = useState<string>('off'); // 'off' | 'all' | size name
  // Curves / colour panel selections, and the armed white-balance eyedropper.
  const [curveChannel, setCurveChannel] = useState<CurveChannel>('rgb');
  const [hslBand, setHslBand] = useState<HslBandKey>('orange'); // skin tones first
  const [picking, setPicking] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [stageBox, setStageBox] = useState({ w: 0, h: 0 });
  // The ops an in-progress gesture (slider drag, crop drag) started from — pushed
  // onto the undo stack once, when the gesture ends, so one drag is one undo step.
  const gestureBase = useRef<EditOps | null>(null);

  // ── Load the image's current bytes ────────────────────────────────────────
  // Editing always starts from the live version (what the card shows and what the
  // export would use). Reloads after a save, so edits stack on the saved result.
  useEffect(() => {
    if (imageId === null) return;
    let active = true;
    let url: string | null = null;
    setSource(null);
    setOps(DEFAULT_OPS);
    setUndoStack([]);
    setRedoStack([]);
    setError(null);
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setPicking(false);
    api
      .bannerImageObjectUrl(briefId, imageId)
      .then((u) => {
        url = u;
        return loadImage(u);
      })
      .then((img) => {
        if (active) setSource(img);
      })
      .catch(() => active && setError('Could not load this image.'))
      .finally(() => {
        // The decoded HTMLImageElement keeps its own copy of the bitmap, so the
        // object URL can go as soon as it has loaded.
        if (url) URL.revokeObjectURL(url);
      });
    return () => {
      active = false;
    };
  }, [briefId, imageId, image?.updated_at]);

  // Escape closes; lock the page behind the dialog.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !saving) onClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, saving, onClose]);

  // Track the stage size so the preview is rendered at display resolution.
  useEffect(() => {
    const el = stageRef.current;
    if (!el) return;
    const measure = () => setStageBox({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [open]);

  const frame = useMemo(
    () => (source ? orientedSize(source, ops) : { w: 1, h: 1 }),
    [source, ops],
  );
  const frameRatio = frame.w / frame.h;
  const outSize = useMemo(
    () => (source ? croppedSize(source, ops) : { w: 0, h: 0 }),
    [source, ops],
  );

  // ── Preview render ───────────────────────────────────────────────────────
  // Cropping shows the whole straightened frame (with the cut-away area masked),
  // so the Designer can see what they're removing; every other tool shows the
  // cropped result. Comparison holds render the untouched original.
  const cropping = tool === 'crop';

  // The displayed size is computed rather than left to CSS `max-h-full`: the crop
  // overlay is positioned in percentages of this box, so it has to match the
  // painted pixels exactly.
  const display = useMemo(() => {
    if (!source || !stageBox.w || !stageBox.h) return null;
    const shown = compare
      ? sourceSize(source)
      : cropping
        ? frame
        : croppedSize(source, ops);
    const aspect = shown.w / shown.h;
    let w = stageBox.w;
    let h = w / aspect;
    if (h > stageBox.h) {
      h = stageBox.h;
      w = h * aspect;
    }
    return { w, h };
  }, [source, stageBox.w, stageBox.h, compare, cropping, frame, ops]);

  /** True scale of the preview against the saved pixels, for the zoom readout. */
  const scalePct = display && outSize.w ? Math.round(((display.w * zoom) / outSize.w) * 100) : 100;
  /** The zoom that shows the edit at exactly 1:1 with the pixels that get saved. */
  const zoomFor100 = display && display.w ? outSize.w / display.w : 1;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !source) return;
    let frameId = 0;
    frameId = requestAnimationFrame(() => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      // Render for the size actually on screen, zoom included, so a 1:1 inspection
      // shows real pixels rather than an upscaled preview.
      const onScreen = Math.max(stageBox.w, stageBox.h) * zoom * dpr;
      const cap = interacting
        ? PREVIEW_INTERACTIVE_EDGE
        : zoom > 1
          ? PREVIEW_MAX_EDGE_ZOOMED
          : PREVIEW_MAX_EDGE;
      const maxEdge = Math.min(cap, Math.max(640, Math.round(onScreen)));
      try {
        const out = renderEdit(source, compare ? DEFAULT_OPS : ops, {
          maxEdge,
          ignoreCrop: cropping && !compare,
        });
        // Read the histogram off the rendered result *before* any clipping marks
        // are painted on, so the marks can't feed back into the numbers.
        setHistogram(histogramOf(out));
        canvas.width = out.width;
        canvas.height = out.height;
        const ctx = canvas.getContext('2d');
        ctx?.drawImage(out, 0, 0);
        // Clipping warnings are a view of the preview only — never of `out`, which
        // is the same pipeline the save re-runs.
        if (showClipping && !compare) markClipping(canvas);
      } catch {
        setError('Could not render the preview in this browser.');
      }
    });
    return () => cancelAnimationFrame(frameId);
  }, [source, ops, compare, cropping, stageBox.w, stageBox.h, zoom, interacting, showClipping]);

  // ── Zoom & pan ───────────────────────────────────────────────────────────
  // Panning is bounded so the image can never be dragged fully out of the stage.
  const clampPan = useCallback(
    (next: { x: number; y: number }, atZoom: number) => {
      if (!display) return { x: 0, y: 0 };
      const slackX = Math.max(0, (display.w * atZoom - stageBox.w) / 2);
      const slackY = Math.max(0, (display.h * atZoom - stageBox.h) / 2);
      return {
        x: clampNum(next.x, -slackX, slackX),
        y: clampNum(next.y, -slackY, slackY),
      };
    },
    [display, stageBox.w, stageBox.h],
  );

  // A hero smaller than the stage is already displayed *above* 100%, so reaching
  // 1:1 means zooming out past the fit — hence a lower bound below 1 in that case.
  const minZoom = Math.min(1, zoomFor100);

  const zoomTo = useCallback(
    (next: number, focus?: { x: number; y: number }) => {
      const target = clampNum(next, minZoom, Math.max(MAX_ZOOM, zoomFor100));
      setZoom(target);
      setPan((cur) => {
        if (target <= 1) return { x: 0, y: 0 };
        // Keep the point under the cursor fixed while the scale changes.
        const k = target / zoom;
        const fx = focus?.x ?? 0;
        const fy = focus?.y ?? 0;
        return clampPan({ x: (cur.x - fx) * k + fx, y: (cur.y - fy) * k + fy }, target);
      });
    },
    [zoom, zoomFor100, minZoom, clampPan],
  );

  const onStageWheel = (e: React.WheelEvent) => {
    if (!display) return;
    e.preventDefault();
    const box = stageRef.current?.getBoundingClientRect();
    const focus = box
      ? { x: e.clientX - (box.x + box.width / 2), y: e.clientY - (box.y + box.height / 2) }
      : undefined;
    zoomTo(zoom * (1 - e.deltaY * 0.0015), focus);
  };

  // Drag-to-pan. In crop mode the frame and its handles stop propagation first, so
  // only a drag on the masked-away area pans.
  const panDrag = useRef<{ x: number; y: number; from: { x: number; y: number } } | null>(null);
  const onStagePointerDown = (e: React.PointerEvent) => {
    if (zoom <= 1 || picking) return;
    panDrag.current = { x: e.clientX, y: e.clientY, from: pan };
  };
  const onStagePointerMove = (e: React.PointerEvent) => {
    const d = panDrag.current;
    if (!d) return;
    setPan(clampPan({ x: d.from.x + (e.clientX - d.x), y: d.from.y + (e.clientY - d.y) }, zoom));
  };
  const onStagePointerUp = () => {
    panDrag.current = null;
  };

  // ── Ops mutation + undo/redo ─────────────────────────────────────────────
  /** A discrete change (button press, preset) — one undo step. */
  const apply = useCallback(
    (next: EditOps | ((cur: EditOps) => EditOps)) => {
      setUndoStack((s) => [...s, ops]);
      setRedoStack([]);
      setOps(typeof next === 'function' ? next(ops) : next);
    },
    [ops],
  );

  // A drag (slider or crop handle) is one undo step, not one per pixel of travel:
  // the pre-gesture state is banked on pointer-down and committed on release. The
  // `interacting` flag also drops the preview resolution for the duration.
  const beginGesture = useCallback(() => {
    if (gestureBase.current === null) gestureBase.current = ops;
    setInteracting(true);
  }, [ops]);

  const endGesture = useCallback(() => {
    const base = gestureBase.current;
    gestureBase.current = null;
    setInteracting(false);
    if (base === null || base === ops) return; // nothing actually moved
    setUndoStack((s) => [...s, base]);
    setRedoStack([]);
  }, [ops]);

  const undo = useCallback(() => {
    if (!undoStack.length) return;
    setOps(undoStack[undoStack.length - 1]);
    setUndoStack((s) => s.slice(0, -1));
    setRedoStack((r) => [...r, ops]);
  }, [undoStack, ops]);

  const redo = useCallback(() => {
    if (!redoStack.length) return;
    setOps(redoStack[redoStack.length - 1]);
    setRedoStack((r) => r.slice(0, -1));
    setUndoStack((u) => [...u, ops]);
  }, [redoStack, ops]);

  const resetAll = () => apply(DEFAULT_OPS);

  const setAdj = (key: keyof Adjustments, value: number) =>
    setOps((cur) => ({ ...cur, adj: { ...cur.adj, [key]: value } }));

  const setCrop = (rect: CropRect, ratio: number | null) =>
    setOps((cur) => ({ ...cur, crop: normalizeCrop(rect, ratio, frameRatio) }));

  const pickAspect = (key: string, ratio: number | null) => {
    if (ratio === null) {
      apply((cur) => ({ ...cur, aspect: 'free' }));
      return;
    }
    // "Original" (ratio 0) means the frame's own shape — a full-frame crop.
    const target = ratio === 0 ? frameRatio : ratio;
    apply((cur) => ({ ...cur, aspect: key, crop: cropForAspect(target, frameRatio) }));
  };

  const rotateBy = (turn: 1 | -1) =>
    apply((cur) => ({
      ...cur,
      // The frame's shape changes, so any existing crop no longer means the same
      // thing — reset it rather than silently reframing the shot.
      rotate: (((cur.rotate / 90 + turn + 4) % 4) * 90) as EditOps['rotate'],
      crop: FULL_CROP,
      aspect: cur.aspect === 'free' ? 'free' : null,
    }));

  const flip = (axis: 'h' | 'v') =>
    apply((cur) => ({
      ...cur,
      flipH: axis === 'h' ? !cur.flipH : cur.flipH,
      flipV: axis === 'v' ? !cur.flipV : cur.flipV,
      // A flip mirrors the frame, so mirror the crop with it.
      crop:
        axis === 'h'
          ? { ...cur.crop, x: 1 - cur.crop.x - cur.crop.w }
          : { ...cur.crop, y: 1 - cur.crop.y - cur.crop.h },
    }));

  const activeRatio = useMemo(() => {
    const preset = ASPECT_PRESETS.find((p) => p.key === ops.aspect);
    if (!preset || preset.ratio === null) return null;
    return preset.ratio === 0 ? frameRatio : preset.ratio;
  }, [ops.aspect, frameRatio]);

  // ── Curves & colour ──────────────────────────────────────────────────────
  const setCurve = (channel: CurveChannel, points: CurvePoint[]) =>
    setOps((cur) => ({ ...cur, curves: { ...cur.curves, [channel]: points } }));

  const setBand = (band: HslBandKey, part: 'h' | 's' | 'l', value: number) =>
    setOps((cur) => ({
      ...cur,
      hsl: { ...cur.hsl, [band]: { ...cur.hsl[band], [part]: value } },
    }));

  /** Sample a point the Designer says should be neutral and land Warmth/Tint on it.
   *
   *  The sample has to come from a render with Warmth and Tint at zero, otherwise
   *  the correction would be measured against a cast this tool is about to replace
   *  — so this renders the current edit minus white balance and reads that.
   */
  const pickWhiteBalance = (u: number, v: number) => {
    if (!source) return;
    setPicking(false);
    try {
      const probe = renderEdit(
        source,
        { ...ops, adj: { ...ops.adj, warmth: 0, tint: 0 } },
        { maxEdge: 700, ignoreCrop: cropping },
      );
      const px = clampNum(Math.round(u * probe.width), 0, probe.width - 1);
      const py = clampNum(Math.round(v * probe.height), 0, probe.height - 1);
      // Average a small patch so a single noisy pixel can't set the whole grade.
      const x0 = Math.max(0, px - 2);
      const y0 = Math.max(0, py - 2);
      const w = Math.min(5, probe.width - x0);
      const h = Math.min(5, probe.height - y0);
      const d = probe.getContext('2d')!.getImageData(x0, y0, w, h).data;
      let r = 0;
      let g = 0;
      let b = 0;
      for (let i = 0; i < d.length; i += 4) {
        r += d[i];
        g += d[i + 1];
        b += d[i + 2];
      }
      const n = d.length / 4;
      const wb = neutralizeFrom(r / n, g / n, b / n);
      apply((cur) => ({ ...cur, adj: { ...cur.adj, warmth: wb.warmth, tint: wb.tint } }));
    } catch {
      setError('Could not sample that point.');
    }
  };

  /** Click-to-sample while the eyedropper is armed: stage coords → image coords. */
  const onPickPoint = (e: React.PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const box = canvas.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) return;
    pickWhiteBalance((e.clientX - box.x) / box.width, (e.clientY - box.y) / box.height);
  };

  // ── Save ─────────────────────────────────────────────────────────────────
  const save = async () => {
    if (!source || imageId === null || isNeutral(ops)) return;
    setSaving(true);
    setError(null);
    try {
      // Re-run the identical pipeline at full resolution — the preview was only
      // ever a downscale of this.
      const full = renderEdit(source, ops);
      const { blob, type } = await encodeCanvas(full, MAX_SAVE_BYTES);
      const file = new File([blob], `hero-edit.${type === 'image/png' ? 'png' : 'jpg'}`, { type });
      const { image: updated } = await api.manualEditBannerImage(
        briefId,
        imageId,
        file,
        describeOps(ops),
      );
      // The saved result is now the live version; the load effect re-reads it and
      // clears the ops, so the next edit stacks on top of this one.
      onUpdated(updated);
    } catch (e) {
      setError(
        e instanceof ApiError || e instanceof Error ? e.message : 'Could not save the edit.',
      );
    } finally {
      setSaving(false);
    }
  };

  const dirty = !isNeutral(ops);

  if (!open || imageId === null) return null;

  return createPortal(
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.18 }}
      >
        <div
          className="absolute inset-0 bg-black/55 backdrop-blur-sm"
          onClick={() => !saving && onClose()}
          aria-hidden
        />

        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="Design Studio — manual edit"
          initial={{ opacity: 0, scale: 0.97, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.98, y: 6 }}
          transition={{ type: 'spring', stiffness: 360, damping: 30 }}
          className="relative w-full max-w-[100rem] h-[94vh] flex flex-col rounded-2xl bg-bg shadow-elevated overflow-hidden"
        >
          {/* Header — title, the AI/manual switch, close */}
          <header className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3 hairline-b shrink-0">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-headline text-label">
                <Sliders size={17} className="text-accent shrink-0" /> Design Studio
              </div>
              <p className="text-caption text-label-tertiary line-clamp-1 mt-0.5">{headline}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {onSwitchToAi && (
                <Button variant="plain" size="sm" onClick={onSwitchToAi} disabled={saving}>
                  <Wand2 size={14} /> <span className="hidden sm:inline">Edit with AI</span>
                </Button>
              )}
              <button
                onClick={() => !saving && onClose()}
                aria-label="Close"
                className="grid place-items-center h-9 w-9 -mr-1.5 rounded-full text-label-secondary hover:bg-fill-quaternary focus-ring"
              >
                <X size={18} />
              </button>
            </div>
          </header>

          <div className="flex-1 min-h-0 flex flex-col lg:flex-row">
            {/* Stage — the live canvas, with the crop frame, template guides and
                the zoom/pan viewport layered over it */}
            <div className="flex-1 min-h-0 min-w-0 bg-bg-secondary p-3 sm:p-5 select-none">
              <div
                ref={stageRef}
                onWheel={onStageWheel}
                onPointerDown={onStagePointerDown}
                onPointerMove={onStagePointerMove}
                onPointerUp={onStagePointerUp}
                onPointerLeave={onStagePointerUp}
                className={cn(
                  'relative h-full w-full grid place-items-center overflow-hidden',
                  picking && 'cursor-crosshair',
                  !picking && zoom > 1 && 'cursor-grab',
                )}
              >
                {source === null || display === null ? (
                  <span
                    className="h-7 w-7 rounded-full border-2 border-separator border-t-accent animate-spin"
                    aria-label="Loading image"
                  />
                ) : (
                  <div
                    className="relative leading-none"
                    style={{
                      width: display.w * zoom,
                      height: display.h * zoom,
                      transform: `translate(${pan.x}px, ${pan.y}px)`,
                    }}
                  >
                    <canvas
                      ref={canvasRef}
                      className="block h-full w-full rounded-md shadow-card"
                    />
                    {cropping && !compare && (
                      <>
                        {/* Template guides sit under the crop frame so the frame's
                            handles stay grabbable. */}
                        <GuideOverlay
                          guides={guides ?? null}
                          mode={guideMode}
                          crop={ops.crop}
                          frameRatio={frameRatio}
                        />
                        <CropOverlay
                          crop={ops.crop}
                          ratio={activeRatio}
                          frameRatio={frameRatio}
                          onBegin={beginGesture}
                          onChange={(rect) => setCrop(rect, activeRatio)}
                          onEnd={endGesture}
                        />
                      </>
                    )}
                    {/* While the eyedropper is armed it takes every click, so it
                        can't fight the crop frame underneath. */}
                    {picking && (
                      <div
                        className="absolute inset-0 z-20 cursor-crosshair"
                        onPointerDown={(e) => {
                          e.stopPropagation();
                          onPickPoint(e);
                        }}
                      />
                    )}
                    {compare && (
                      <span className="absolute left-2 top-2 rounded-full bg-black/65 px-2.5 py-1 text-caption2 font-semibold text-white">
                        Original
                      </span>
                    )}
                  </div>
                )}

                {picking && (
                  <div className="absolute inset-x-0 bottom-2 flex justify-center pointer-events-none">
                    <span className="rounded-full bg-black/75 px-3 py-1.5 text-caption2 font-semibold text-white">
                      Click something that should be neutral grey or white
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Tool rail + the active tool's controls */}
            <div className="w-full lg:w-[340px] shrink-0 flex flex-col border-t lg:border-t-0 lg:border-l border-separator min-h-0">
              {/* Histogram stays visible whatever tool is open — it's how you catch
                  blown skin highlights before the approval gate. */}
              <div className="shrink-0 px-4 pt-3 pb-2.5 hairline-b">
                <HistogramPanel
                  histogram={histogram}
                  showClipping={showClipping}
                  onToggleClipping={() => setShowClipping((v) => !v)}
                />
              </div>

              <div className="flex gap-1 px-2 py-2 hairline-b shrink-0">
                {TOOLS.map((t) => {
                  const active = t.key === tool;
                  const Icon = t.icon;
                  return (
                    <div key={t.key} className="group relative flex-1">
                      <button
                        onClick={() => setTool(t.key)}
                        aria-pressed={active}
                        aria-label={t.label}
                        className={cn(
                          'flex w-full items-center justify-center rounded-md py-1.5 focus-ring',
                          active
                            ? 'bg-[color:var(--color-accent-soft)] text-accent'
                            : 'text-label-secondary hover:bg-fill-quaternary',
                        )}
                      >
                        <Icon size={16} />
                      </button>
                      <span
                        role="tooltip"
                        className="pointer-events-none absolute top-full left-1/2 z-10 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md border border-separator bg-bg-tertiary px-2 py-1 text-caption2 font-semibold text-label opacity-0 shadow-card transition-opacity delay-150 duration-150 group-hover:opacity-100"
                      >
                        {t.label}
                      </span>
                    </div>
                  );
                })}
              </div>

              <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 max-h-[38vh] lg:max-h-none">
                {tool === 'crop' && (
                  <CropPanel
                    ops={ops}
                    outSize={outSize}
                    guides={guides ?? null}
                    guideMode={guideMode}
                    onGuideMode={setGuideMode}
                    onPickAspect={pickAspect}
                    onResetCrop={() => apply((cur) => ({ ...cur, crop: FULL_CROP, aspect: 'free' }))}
                  />
                )}

                {tool === 'rotate' && (
                  <div className="space-y-4">
                    <ToolHeading
                      title="Rotate & straighten"
                      hint="Quarter turns and flips, plus a fine straighten that scales the photo to keep the corners filled."
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <Button variant="glass" size="sm" onClick={() => rotateBy(-1)}>
                        <RotateCcw size={14} /> Rotate left
                      </Button>
                      <Button variant="glass" size="sm" onClick={() => rotateBy(1)}>
                        <RotateCw size={14} /> Rotate right
                      </Button>
                      <Button variant="glass" size="sm" onClick={() => flip('h')}>
                        <FlipHorizontal2 size={14} /> Flip across
                      </Button>
                      <Button variant="glass" size="sm" onClick={() => flip('v')}>
                        <FlipVertical2 size={14} /> Flip down
                      </Button>
                    </div>
                    <Slider
                      label="Straighten"
                      value={ops.straighten}
                      min={-45}
                      max={45}
                      step={0.1}
                      digits={1}
                      suffix="°"
                      onBegin={beginGesture}
                      onChange={(v) => setOps((cur) => ({ ...cur, straighten: v }))}
                      onEnd={endGesture}
                      onReset={() => apply((cur) => ({ ...cur, straighten: 0 }))}
                    />
                    <p className="text-caption2 text-label-tertiary">
                      Rotating a quarter turn changes the frame's shape, so it resets the crop.
                    </p>
                  </div>
                )}

                {tool === 'tune' && (
                  <div className="space-y-4">
                    {/* One click on a known neutral beats hunting for the cast with
                        the Warmth and Tint sliders. */}
                    <Button
                      variant={picking ? 'filled' : 'glass'}
                      size="sm"
                      className="w-full"
                      onClick={() => setPicking((v) => !v)}
                    >
                      <Pipette size={14} />
                      {picking ? 'Click a neutral in the photo…' : 'Pick white balance'}
                    </Button>
                    <SliderGroup
                      title="Tune image"
                      hint="The tonal pass — light, colour and the two ends of the histogram."
                      keys={TUNE_KEYS}
                      adj={ops.adj}
                      onBegin={beginGesture}
                      onChange={setAdj}
                      onEnd={endGesture}
                      onReset={(k) => apply((cur) => ({ ...cur, adj: { ...cur.adj, [k]: 0 } }))}
                    />
                  </div>
                )}

                {tool === 'curves' && (
                  <CurvesPanel
                    curves={ops.curves}
                    channel={curveChannel}
                    histogram={histogram}
                    onChannel={setCurveChannel}
                    onBegin={beginGesture}
                    onChange={(pts) => setCurve(curveChannel, pts)}
                    onEnd={endGesture}
                    onResetChannel={() =>
                      apply((cur) => ({
                        ...cur,
                        curves: { ...cur.curves, [curveChannel]: IDENTITY_CURVE },
                      }))
                    }
                    onResetAll={() => apply((cur) => ({ ...cur, curves: IDENTITY_CURVES }))}
                  />
                )}

                {tool === 'colour' && (
                  <HslPanel
                    hsl={ops.hsl}
                    band={hslBand}
                    onBand={setHslBand}
                    onBegin={beginGesture}
                    onChange={setBand}
                    onEnd={endGesture}
                    onResetPart={(b, part) =>
                      apply((cur) => ({
                        ...cur,
                        hsl: { ...cur.hsl, [b]: { ...cur.hsl[b], [part]: 0 } },
                      }))
                    }
                    onResetBand={() =>
                      apply((cur) => ({
                        ...cur,
                        hsl: { ...cur.hsl, [hslBand]: { h: 0, s: 0, l: 0 } },
                      }))
                    }
                    onResetAll={() => apply((cur) => ({ ...cur, hsl: NEUTRAL_HSL }))}
                  />
                )}

                {tool === 'details' && (
                  <SliderGroup
                    title="Details"
                    hint="Sharpen works on edge detail; structure works on local contrast and can go negative to soften skin."
                    keys={DETAIL_KEYS}
                    adj={ops.adj}
                    onBegin={beginGesture}
                    onChange={setAdj}
                    onEnd={endGesture}
                    onReset={(k) => apply((cur) => ({ ...cur, adj: { ...cur.adj, [k]: 0 } }))}
                  />
                )}

                {tool === 'effects' && (
                  <SliderGroup
                    title="Effects"
                    hint="Keep these restrained — the banner frame sits over this photo."
                    keys={EFFECT_KEYS}
                    adj={ops.adj}
                    onBegin={beginGesture}
                    onChange={setAdj}
                    onEnd={endGesture}
                    onReset={(k) => apply((cur) => ({ ...cur, adj: { ...cur.adj, [k]: 0 } }))}
                  />
                )}
              </div>

              {/* Edit summary — the same line that lands in the version history */}
              <div className="shrink-0 px-4 py-3 hairline-t">
                <p className="text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">
                  This edit
                </p>
                <p className="text-caption text-label-secondary mt-1 line-clamp-3">
                  {dirty ? describeOps(ops) : 'Nothing changed yet — pick a tool above.'}
                </p>
              </div>
            </div>
          </div>

          {/* Footer — history, compare, output size, save */}
          <footer className="shrink-0 px-4 py-3 hairline-t glass">
            <AnimatePresence>
              {error && (
                <motion.p
                  className="flex items-center gap-1.5 text-footnote text-error mb-2"
                  role="alert"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                >
                  <AlertCircle size={14} className="shrink-0" /> {error}
                </motion.p>
              )}
            </AnimatePresence>

            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-1.5 flex-wrap">
                <Button
                  variant="plain"
                  size="sm"
                  onClick={undo}
                  disabled={!undoStack.length || saving}
                >
                  <Undo2 size={14} /> Undo
                </Button>
                <Button
                  variant="plain"
                  size="sm"
                  onClick={redo}
                  disabled={!redoStack.length || saving}
                >
                  <Redo2 size={14} /> Redo
                </Button>
                <Button
                  variant="plain"
                  size="sm"
                  onClick={resetAll}
                  disabled={!dirty || saving}
                >
                  <RefreshCw size={14} /> Reset all
                </Button>
                {/* Hold to see the untouched original — press-and-hold, like a loupe. */}
                <Button
                  variant="glass"
                  size="sm"
                  disabled={!dirty || saving}
                  onPointerDown={() => setCompare(true)}
                  onPointerUp={() => setCompare(false)}
                  onPointerLeave={() => setCompare(false)}
                  onBlur={() => setCompare(false)}
                >
                  <Eye size={14} /> Hold to compare
                </Button>
              </div>

              {/* Zoom — fit for framing, 1:1 for judging sharpness and grain. */}
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => zoomTo(zoom / 1.5)}
                  disabled={zoom <= minZoom}
                  aria-label="Zoom out"
                  className="grid place-items-center h-8 w-8 rounded-md text-label-secondary hover:bg-fill-quaternary focus-ring disabled:opacity-40"
                >
                  <ZoomOut size={15} />
                </button>
                <span className="text-caption tabular-nums text-label-secondary w-12 text-center">
                  {scalePct}%
                </span>
                <button
                  type="button"
                  onClick={() => zoomTo(zoom * 1.5)}
                  aria-label="Zoom in"
                  className="grid place-items-center h-8 w-8 rounded-md text-label-secondary hover:bg-fill-quaternary focus-ring"
                >
                  <ZoomIn size={15} />
                </button>
                <Button
                  variant="plain"
                  size="sm"
                  onClick={() => (zoom === 1 ? zoomTo(zoomFor100) : zoomTo(1))}
                >
                  <Maximize2 size={13} /> {zoom === 1 ? '100%' : 'Fit'}
                </Button>
              </div>

              <div className="flex items-center gap-2.5 flex-wrap">
                {outSize.w > 0 && (
                  <Pill className="bg-fill-quaternary text-label-secondary tabular-nums">
                    {outSize.w}×{outSize.h}px
                  </Pill>
                )}
                <Button onClick={save} disabled={!dirty || saving || !source}>
                  <Check size={15} /> {saving ? 'Saving…' : 'Save as new version'}
                </Button>
              </div>
            </div>
            <p className="text-caption2 text-label-tertiary mt-1.5">
              <Sparkles size={11} className="inline -mt-0.5 mr-1 text-accent" />
              Saving adds a version to this image's history — the old one stays selectable, and the
              set needs re-approving before export.
            </p>
          </footer>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body,
  );
}

// ── Histogram ────────────────────────────────────────────────────────────────
const HIST_W = 256;
const HIST_H = 68;

/** The always-visible histogram: the three channels drawn over each other, plus
 *  the share of the frame that is blown or crushed and a toggle that paints those
 *  pixels on the preview. Judging exposure by eye on a bright screen is how a hero
 *  with clipped skin highlights reaches the approval gate. */
function HistogramPanel({
  histogram,
  showClipping,
  onToggleClipping,
}: {
  histogram: Histogram | null;
  showClipping: boolean;
  onToggleClipping: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, HIST_W, HIST_H);
    if (!histogram) return;

    // Scale to the tallest bin, ignoring the two ends: a large flat black or white
    // area otherwise flattens everything else into the baseline.
    let peak = 1;
    for (const ch of [histogram.r, histogram.g, histogram.b]) {
      for (let i = 1; i < 255; i++) if (ch[i] > peak) peak = ch[i];
    }
    ctx.globalCompositeOperation = 'lighter';
    const channels: [Uint32Array, string][] = [
      [histogram.r, 'rgba(229,72,77,0.75)'],
      [histogram.g, 'rgba(48,164,108,0.75)'],
      [histogram.b, 'rgba(0,145,255,0.75)'],
    ];
    for (const [bins, fill] of channels) {
      ctx.beginPath();
      ctx.moveTo(0, HIST_H);
      for (let i = 0; i < 256; i++) {
        const v = Math.min(1, bins[i] / peak);
        ctx.lineTo(i, HIST_H - v * (HIST_H - 2));
      }
      ctx.lineTo(255, HIST_H);
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
  }, [histogram]);

  const pct = (n: number) =>
    histogram && histogram.total ? (n / histogram.total) * 100 : 0;
  const high = pct(histogram?.clippedHigh ?? 0);
  const low = pct(histogram?.clippedLow ?? 0);
  const fmt = (v: number) => (v === 0 ? '0' : v < 0.1 ? '<0.1' : v.toFixed(1));

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <p className="text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">
          Histogram
        </p>
        <button
          type="button"
          onClick={onToggleClipping}
          aria-pressed={showClipping}
          className={cn(
            'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-caption2 font-semibold focus-ring',
            showClipping
              ? 'bg-[color:var(--color-accent-soft)] text-accent'
              : 'text-label-tertiary hover:bg-fill-quaternary',
          )}
        >
          <AlertTriangle size={11} /> Show clipping
        </button>
      </div>
      <canvas
        ref={canvasRef}
        width={HIST_W}
        height={HIST_H}
        className="block w-full rounded-md bg-[color:var(--color-fill-quaternary)]"
        style={{ height: HIST_H }}
      />
      <div className="flex items-center justify-between gap-2 mt-1 text-caption2 tabular-nums">
        <span className={cn(low > 1 ? 'text-[color:#0091ff] font-semibold' : 'text-label-tertiary')}>
          Crushed {fmt(low)}%
        </span>
        <span className={cn(high > 1 ? 'text-error font-semibold' : 'text-label-tertiary')}>
          Blown {fmt(high)}%
        </span>
      </div>
    </div>
  );
}

// ── Template crop guides ─────────────────────────────────────────────────────
/** Draw what the export will actually keep.
 *
 *  The hero is placed with FILL, i.e. centre-cropped, so for each ad format the
 *  visible slice of the current crop is the largest centred rectangle of that
 *  format's hero aspect. "Every format" shows the intersection of all of them — the
 *  band the subject has to sit inside to survive the whole set — and a single
 *  format additionally shows the copy column, where copy is laid over the photo.
 */
function GuideOverlay({
  guides,
  mode,
  crop,
  frameRatio,
}: {
  guides: HeroGuides | null;
  mode: string;
  crop: CropRect;
  frameRatio: number;
}) {
  if (!guides || mode === 'off' || guides.crops.length === 0) return null;

  // The crop rect's own pixel aspect — the shape the export starts from.
  const cropAspect = (crop.w / crop.h) * frameRatio;

  // A centred box of `aspect` inside the crop, as fractions OF THE CROP.
  const boxFor = (aspect: number) => {
    if (aspect >= cropAspect) {
      const h = cropAspect / aspect;
      return { x: 0, y: (1 - h) / 2, w: 1, h };
    }
    const w = aspect / cropAspect;
    return { x: (1 - w) / 2, y: 0, w, h: 1 };
  };

  const single = mode === 'all' ? null : guides.crops.find((c) => c.name === mode) ?? null;
  // A named format this template doesn't have — draw nothing rather than silently
  // falling back to a different guide than the one that was asked for.
  if (mode !== 'all' && single === null) return null;
  // Worst case in both directions: the widest crop bounds the height, the tallest
  // bounds the width. For inexact layouts that means using the range's extremes.
  const widest = Math.max(...guides.crops.map((c) => c.max));
  const tallest = Math.min(...guides.crops.map((c) => c.min));
  const shown = single
    ? [{ label: single.name, box: boxFor(single.aspect), solid: true }]
    : [
        {
          label: 'Safe for every format',
          box: {
            x: Math.max(boxFor(widest).x, boxFor(tallest).x),
            y: Math.max(boxFor(widest).y, boxFor(tallest).y),
            w: Math.min(boxFor(widest).w, boxFor(tallest).w),
            h: Math.min(boxFor(widest).h, boxFor(tallest).h),
          },
          solid: true,
        },
      ];

  // Guides are drawn inside the crop rect, so position everything relative to it.
  const pct = (v: number) => `${v * 100}%`;
  return (
    <div
      className="absolute pointer-events-none z-10"
      style={{ left: pct(crop.x), top: pct(crop.y), width: pct(crop.w), height: pct(crop.h) }}
    >
      {shown.map((g) => (
        <div
          key={g.label}
          className="absolute border-2 border-dashed border-[color:var(--color-accent)]"
          style={{
            left: pct(g.box.x),
            top: pct(g.box.y),
            width: pct(g.box.w),
            height: pct(g.box.h),
          }}
        >
          <span className="absolute -top-0.5 left-1 -translate-y-full whitespace-nowrap rounded bg-accent px-1.5 py-0.5 text-caption2 font-semibold text-[color:var(--color-on-accent)]">
            {g.label}
          </span>
        </div>
      ))}

      {/* Copy column — only meaningful when copy is laid over the photo. */}
      {single && guides.copy && (
        <div
          className="absolute border border-white/70 bg-black/35"
          style={{
            left: pct(guides.copy.x0),
            top: 0,
            width: pct(guides.copy.x1 - guides.copy.x0),
            height: pct(1 - guides.copy.footer),
          }}
        >
          <span className="absolute bottom-1 left-1 rounded bg-black/70 px-1.5 py-0.5 text-caption2 font-semibold text-white">
            Copy sits here
          </span>
        </div>
      )}
    </div>
  );
}

// ── Crop panel ───────────────────────────────────────────────────────────────
function CropPanel({
  ops,
  outSize,
  guides,
  guideMode,
  onGuideMode,
  onPickAspect,
  onResetCrop,
}: {
  ops: EditOps;
  outSize: { w: number; h: number };
  guides: HeroGuides | null;
  guideMode: string;
  onGuideMode: (mode: string) => void;
  onPickAspect: (key: string, ratio: number | null) => void;
  onResetCrop: () => void;
}) {
  return (
    <div className="space-y-4">
      <ToolHeading
        title="Crop"
        hint="Drag the frame or its handles on the photo. Lock a shape first if the crop has to match an ad format."
      />
      <div className="grid grid-cols-3 gap-2">
        {ASPECT_PRESETS.map((p) => {
          const active = (ops.aspect ?? 'free') === p.key;
          return (
            <button
              key={p.key}
              onClick={() => onPickAspect(p.key, p.ratio)}
              aria-pressed={active}
              className={cn(
                'rounded-md border px-2 py-1.5 text-caption font-semibold focus-ring',
                active
                  ? 'border-accent bg-accent/5 text-accent'
                  : 'border-separator text-label-secondary hover:bg-fill-quaternary',
              )}
            >
              {p.label}
            </button>
          );
        })}
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-caption text-label-tertiary tabular-nums">
          Output {outSize.w}×{outSize.h}
        </span>
        <Button variant="plain" size="sm" onClick={onResetCrop}>
          <RefreshCw size={14} /> Full frame
        </Button>
      </div>

      {/* Format guides — what each ad size will actually keep of this crop. */}
      {guides && guides.crops.length > 0 && (
        <div className="pt-1">
          <p className="flex items-center gap-1.5 text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">
            <LayoutTemplate size={12} /> Format guides
          </p>
          <p className="text-caption text-label-tertiary mt-0.5">
            The export centre-crops this hero into every ad size, so keep the subject inside the
            guide.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <GuideChip label="Off" active={guideMode === 'off'} onClick={() => onGuideMode('off')} />
            <GuideChip
              label="Every format"
              active={guideMode === 'all'}
              onClick={() => onGuideMode('all')}
            />
            {guides.crops.map((c) => (
              <GuideChip
                key={c.name}
                label={AD_SIZE_LABELS[c.name] ?? c.name}
                active={guideMode === c.name}
                onClick={() => onGuideMode(c.name)}
              />
            ))}
          </div>
          {guideMode !== 'off' &&
            (() => {
              const c = guides.crops.find((s) => s.name === guideMode);
              if (c && !c.exact) {
                return (
                  <p className="mt-2 text-caption2 text-label-tertiary">
                    This layout sizes the hero from the copy block, so its crop varies between{' '}
                    {c.min.toFixed(2)}:1 and {c.max.toFixed(2)}:1 — the guide shows the middle.
                  </p>
                );
              }
              if (guideMode === 'all' && guides.crops.some((s) => !s.exact)) {
                return (
                  <p className="mt-2 text-caption2 text-label-tertiary">
                    Uses each format's tightest possible crop, so anything inside survives all of
                    them.
                  </p>
                );
              }
              return null;
            })()}
        </div>
      )}
    </div>
  );
}

function GuideChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'rounded-full border px-2.5 py-1 text-caption2 font-semibold focus-ring',
        active
          ? 'border-accent bg-accent/5 text-accent'
          : 'border-separator text-label-secondary hover:bg-fill-quaternary',
      )}
    >
      {label}
    </button>
  );
}

// ── Curves ───────────────────────────────────────────────────────────────────
const CURVE_SIZE = 256; // the editor works in 0..255 on both axes
const CURVE_HIT = 12; // grab radius, in curve units

/** The tone-curve editor: drag a point, click to add one, double-click to remove.
 *  The channel's histogram is drawn behind the curve so black and white points can
 *  be set against the actual distribution rather than guessed. */
function CurvesPanel({
  curves,
  channel,
  histogram,
  onChannel,
  onBegin,
  onChange,
  onEnd,
  onResetChannel,
  onResetAll,
}: {
  curves: Curves;
  channel: CurveChannel;
  histogram: Histogram | null;
  onChannel: (c: CurveChannel) => void;
  onBegin: () => void;
  onChange: (points: CurvePoint[]) => void;
  onEnd: () => void;
  onResetChannel: () => void;
  onResetAll: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragIndex = useRef<number | null>(null);
  const points = curves[channel];
  const stroke = CURVE_CHANNELS.find((c) => c.key === channel)?.stroke ?? 'currentColor';

  // Repaint the grid, the histogram, the curve and its handles.
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const S = CURVE_SIZE;
    ctx.clearRect(0, 0, S, S);

    const bins =
      histogram &&
      (channel === 'rgb'
        ? histogram.luma
        : channel === 'r'
          ? histogram.r
          : channel === 'g'
            ? histogram.g
            : histogram.b);
    if (bins) {
      let peak = 1;
      for (let i = 1; i < 255; i++) if (bins[i] > peak) peak = bins[i];
      ctx.fillStyle = 'rgba(128,128,128,0.28)';
      ctx.beginPath();
      ctx.moveTo(0, S);
      for (let i = 0; i < 256; i++) ctx.lineTo(i, S - Math.min(1, bins[i] / peak) * S);
      ctx.lineTo(255, S);
      ctx.closePath();
      ctx.fill();
    }

    ctx.strokeStyle = 'rgba(128,128,128,0.35)';
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) {
      const p = (S / 4) * i;
      ctx.beginPath();
      ctx.moveTo(p, 0);
      ctx.lineTo(p, S);
      ctx.moveTo(0, p);
      ctx.lineTo(S, p);
      ctx.stroke();
    }
    // The identity diagonal, for reference.
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(0, S);
    ctx.lineTo(S, 0);
    ctx.stroke();
    ctx.setLineDash([]);

    // The curve itself, straight off the same LUT the render uses.
    const lut = buildCurveLut(points);
    ctx.strokeStyle = stroke === 'currentColor' ? 'rgba(140,140,150,0.95)' : stroke;
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let i = 0; i < 256; i++) {
      const y = S - (lut[i] / 255) * S;
      if (i === 0) ctx.moveTo(i, y);
      else ctx.lineTo(i, y);
    }
    ctx.stroke();

    ctx.fillStyle = stroke === 'currentColor' ? 'rgba(140,140,150,1)' : stroke;
    for (const [px, py] of points) {
      ctx.beginPath();
      ctx.arc(px, S - (py / 255) * S, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.9)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  }, [points, channel, histogram, stroke]);

  /** Pointer position in curve units (0..255, y already un-inverted). */
  const toCurve = (e: React.PointerEvent) => {
    const box = canvasRef.current!.getBoundingClientRect();
    return {
      x: clampNum(((e.clientX - box.x) / box.width) * 255, 0, 255),
      y: clampNum(255 - ((e.clientY - box.y) / box.height) * 255, 0, 255),
    };
  };

  const onPointerDown = (e: React.PointerEvent) => {
    const { x, y } = toCurve(e);
    const hit = points.findIndex((p) => Math.abs(p[0] - x) <= CURVE_HIT && Math.abs(p[1] - y) <= CURVE_HIT * 2);
    onBegin();
    if (hit >= 0) {
      dragIndex.current = hit;
      return;
    }
    // A click on empty space adds a point and starts dragging it.
    const added: CurvePoint = [Math.round(x), Math.round(y)];
    const next: CurvePoint[] = [...points, added].sort((a, b) => a[0] - b[0]);
    dragIndex.current = next.indexOf(added);
    onChange(next);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const i = dragIndex.current;
    if (i === null) return;
    const { x, y } = toCurve(e);
    const next = points.map((p, k) => (k === i ? ([p[0], Math.round(y)] as CurvePoint) : p));
    // Interior points move horizontally too, but can't cross their neighbours.
    if (i > 0 && i < next.length - 1) {
      const lo = next[i - 1][0] + 2;
      const hi = next[i + 1][0] - 2;
      next[i] = [Math.round(clampNum(x, lo, hi)), next[i][1]];
    }
    onChange(next);
  };

  const finish = () => {
    if (dragIndex.current === null) return;
    dragIndex.current = null;
    onEnd();
  };

  const onDoubleClick = (e: React.MouseEvent) => {
    const box = canvasRef.current!.getBoundingClientRect();
    const x = ((e.clientX - box.x) / box.width) * 255;
    const i = points.findIndex((p) => Math.abs(p[0] - x) <= CURVE_HIT);
    // The two end points anchor the curve — everything between them is removable.
    if (i > 0 && i < points.length - 1) onChange(points.filter((_, k) => k !== i));
  };

  return (
    <div className="space-y-3">
      <ToolHeading
        title="Curves"
        hint="Drag to bend the response; click to add a point, double-click to remove one. The grey shape behind is this channel's histogram."
      />
      <div className="flex gap-1">
        {CURVE_CHANNELS.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => onChannel(c.key)}
            aria-pressed={channel === c.key}
            className={cn(
              'flex-1 rounded-md border px-2 py-1 text-caption font-semibold focus-ring',
              channel === c.key
                ? 'border-accent bg-accent/5 text-accent'
                : 'border-separator text-label-secondary hover:bg-fill-quaternary',
            )}
          >
            {c.label}
          </button>
        ))}
      </div>
      <canvas
        ref={canvasRef}
        width={CURVE_SIZE}
        height={CURVE_SIZE}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finish}
        onPointerLeave={finish}
        onDoubleClick={onDoubleClick}
        aria-label={`${channel} tone curve`}
        className="block w-full aspect-square touch-none rounded-md border border-separator bg-bg-secondary text-label-secondary cursor-crosshair"
      />
      <div className="flex items-center justify-between gap-2">
        <Button
          variant="plain"
          size="sm"
          onClick={onResetChannel}
          disabled={isIdentityCurve(points)}
        >
          <RefreshCw size={14} /> Reset {CURVE_CHANNELS.find((c) => c.key === channel)?.label}
        </Button>
        <Button variant="plain" size="sm" onClick={onResetAll} disabled={!curvesTouched(curves)}>
          Reset all
        </Button>
      </div>
    </div>
  );
}

// ── Per-band colour (HSL) ────────────────────────────────────────────────────
/** Hue / saturation / luminance for one colour band at a time. Orange is selected
 *  by default because it is the skin-tone band, and the brand playbook is explicit
 *  about keeping Indian skin tones true — this is the control for that, rather than
 *  pushing global saturation and hoping. */
function HslPanel({
  hsl,
  band,
  onBand,
  onBegin,
  onChange,
  onEnd,
  onResetPart,
  onResetBand,
  onResetAll,
}: {
  hsl: EditOps['hsl'];
  band: HslBandKey;
  onBand: (b: HslBandKey) => void;
  onBegin: () => void;
  onChange: (band: HslBandKey, part: 'h' | 's' | 'l', value: number) => void;
  onEnd: () => void;
  /** Zeroing one slider is a discrete change, so it goes through the undo stack. */
  onResetPart: (band: HslBandKey, part: 'h' | 's' | 'l') => void;
  onResetBand: () => void;
  onResetAll: () => void;
}) {
  const current = hsl[band];
  const meta = HSL_BANDS.find((b) => b.key === band)!;
  const touched = (k: HslBandKey) => hsl[k].h !== 0 || hsl[k].s !== 0 || hsl[k].l !== 0;
  return (
    <div className="space-y-4">
      <ToolHeading
        title="Colour"
        hint="Retune one colour band at a time. Orange is the skin-tone band — use it instead of global saturation on people."
      />
      <div className="grid grid-cols-4 gap-1.5">
        {HSL_BANDS.map((b) => (
          <button
            key={b.key}
            type="button"
            onClick={() => onBand(b.key)}
            aria-pressed={band === b.key}
            title={b.hint ?? b.label}
            className={cn(
              'relative rounded-md border px-1 py-1.5 text-caption2 font-semibold focus-ring',
              band === b.key
                ? 'border-accent text-accent'
                : 'border-separator text-label-secondary hover:bg-fill-quaternary',
            )}
          >
            <span
              className="block h-1.5 w-full rounded-full mb-1"
              style={{ backgroundColor: `hsl(${b.hue} 70% 50%)` }}
            />
            {b.label}
            {touched(b.key) && (
              <span className="absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full bg-accent" />
            )}
          </button>
        ))}
      </div>

      {meta.hint && (
        <p className="text-caption2 text-label-tertiary -mt-2">
          {meta.label}: {meta.hint}
        </p>
      )}

      <div className="space-y-3.5">
        {(
          [
            ['h', 'Hue'],
            ['s', 'Saturation'],
            ['l', 'Luminance'],
          ] as const
        ).map(([part, label]) => (
          <Slider
            key={part}
            label={label}
            value={current[part]}
            min={-100}
            max={100}
            step={1}
            digits={0}
            onBegin={onBegin}
            onChange={(v) => onChange(band, part, v)}
            onEnd={onEnd}
            onReset={() => onResetPart(band, part)}
          />
        ))}
      </div>

      <div className="flex items-center justify-between gap-2">
        <Button variant="plain" size="sm" onClick={onResetBand} disabled={!touched(band)}>
          <RefreshCw size={14} /> Reset {meta.label}
        </Button>
        <Button variant="plain" size="sm" onClick={onResetAll} disabled={!hslTouched(hsl)}>
          Reset all
        </Button>
      </div>
    </div>
  );
}

// ── The draggable crop frame ────────────────────────────────────────────────
type HandleKey = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'move';

const HANDLES: { key: Exclude<HandleKey, 'move'>; className: string; cursor: string }[] = [
  { key: 'nw', className: 'left-0 top-0 -translate-x-1/2 -translate-y-1/2', cursor: 'nwse-resize' },
  { key: 'n', className: 'left-1/2 top-0 -translate-x-1/2 -translate-y-1/2', cursor: 'ns-resize' },
  { key: 'ne', className: 'right-0 top-0 translate-x-1/2 -translate-y-1/2', cursor: 'nesw-resize' },
  { key: 'e', className: 'right-0 top-1/2 translate-x-1/2 -translate-y-1/2', cursor: 'ew-resize' },
  {
    key: 'se',
    className: 'right-0 bottom-0 translate-x-1/2 translate-y-1/2',
    cursor: 'nwse-resize',
  },
  { key: 's', className: 'left-1/2 bottom-0 -translate-x-1/2 translate-y-1/2', cursor: 'ns-resize' },
  { key: 'sw', className: 'left-0 bottom-0 -translate-x-1/2 translate-y-1/2', cursor: 'nesw-resize' },
  { key: 'w', className: 'left-0 top-1/2 -translate-x-1/2 -translate-y-1/2', cursor: 'ew-resize' },
];

/** The crop frame drawn over the uncropped preview: a dimming mask outside it, a
 *  rule-of-thirds grid inside, eight resize handles and drag-to-move. All maths is
 *  in normalized (0..1) frame coordinates; `normalizeCrop` upstream enforces the
 *  bounds and the locked aspect. */
function CropOverlay({
  crop,
  ratio,
  frameRatio,
  onBegin,
  onChange,
  onEnd,
}: {
  crop: CropRect;
  /** Locked pixel aspect (w/h), or null for a free crop. */
  ratio: number | null;
  /** The frame's own pixel aspect — converts `ratio` into normalized space. */
  frameRatio: number;
  onBegin: () => void;
  onChange: (rect: CropRect) => void;
  onEnd: () => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    handle: HandleKey;
    startX: number;
    startY: number;
    start: CropRect;
    box: { w: number; h: number };
  } | null>(null);

  const start = (handle: HandleKey) => (e: React.PointerEvent) => {
    const box = rootRef.current?.getBoundingClientRect();
    if (!box || box.width === 0 || box.height === 0) return;
    e.preventDefault();
    e.stopPropagation();
    // Capture so the drag survives the pointer leaving the handle. A pointer that
    // has already been released throws here, and that must not abort the drag.
    try {
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      /* no capture available — the root's move handler still tracks the drag */
    }
    drag.current = {
      handle,
      startX: e.clientX,
      startY: e.clientY,
      start: crop,
      box: { w: box.width, h: box.height },
    };
    onBegin();
  };

  const move = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = (e.clientX - d.startX) / d.box.w;
    const dy = (e.clientY - d.startY) / d.box.h;
    const s = d.start;
    const right = s.x + s.w;
    const bottom = s.y + s.h;
    let next: CropRect;

    if (d.handle === 'move') {
      next = { ...s, x: s.x + dx, y: s.y + dy };
      // Moving never resizes, so clamp here rather than letting the shared
      // normalizer shrink the rect at the edges.
      next.x = Math.min(Math.max(next.x, 0), 1 - s.w);
      next.y = Math.min(Math.max(next.y, 0), 1 - s.h);
      onChange(next);
      return;
    }

    let { x, y, w, h } = s;
    const MIN = 0.06;
    if (d.handle.includes('w')) {
      x = Math.min(Math.max(s.x + dx, 0), right - MIN);
      w = right - x;
    }
    if (d.handle.includes('e')) {
      w = Math.min(Math.max(s.w + dx, MIN), 1 - x);
    }
    if (d.handle.includes('n')) {
      y = Math.min(Math.max(s.y + dy, 0), bottom - MIN);
      h = bottom - y;
    }
    if (d.handle.includes('s')) {
      h = Math.min(Math.max(s.h + dy, MIN), 1 - y);
    }

    if (ratio) {
      // With a shape locked, the handle drives one axis and the other follows.
      // Side handles drive their own axis and stay centred on the other; corner
      // handles drive width and keep the opposite corner pinned.
      const target = ratio / frameRatio; // normalized w/h
      const verticalOnly = d.handle === 'n' || d.handle === 's';
      if (verticalOnly) {
        w = h * target;
        x = s.x + (s.w - w) / 2;
      } else {
        h = w / target;
        if (d.handle === 'e' || d.handle === 'w') y = s.y + (s.h - h) / 2;
        else if (d.handle.includes('n')) y = bottom - h;
      }
      if (d.handle.includes('w')) x = right - w;
    }
    onChange({ x, y, w, h });
  };

  const finish = (e: React.PointerEvent) => {
    if (!drag.current) return;
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* nothing was captured — the drag still ends below */
    }
    drag.current = null;
    onEnd();
  };

  const pct = (v: number) => `${v * 100}%`;

  return (
    <div ref={rootRef} className="absolute inset-0" onPointerMove={move} onPointerUp={finish} onPointerCancel={finish}>
      {/* Dim what's being cut away — four bands around the crop rect. */}
      <div className="absolute inset-x-0 top-0 bg-black/55" style={{ height: pct(crop.y) }} />
      <div
        className="absolute inset-x-0 bottom-0 bg-black/55"
        style={{ height: pct(Math.max(0, 1 - crop.y - crop.h)) }}
      />
      <div
        className="absolute left-0 bg-black/55"
        style={{ top: pct(crop.y), height: pct(crop.h), width: pct(crop.x) }}
      />
      <div
        className="absolute right-0 bg-black/55"
        style={{
          top: pct(crop.y),
          height: pct(crop.h),
          width: pct(Math.max(0, 1 - crop.x - crop.w)),
        }}
      />

      {/* The frame itself */}
      <div
        className="absolute border-2 border-white/90 cursor-move touch-none"
        style={{ left: pct(crop.x), top: pct(crop.y), width: pct(crop.w), height: pct(crop.h) }}
        onPointerDown={start('move')}
      >
        {/* Rule-of-thirds guides */}
        <div className="pointer-events-none absolute inset-0">
          <span className="absolute left-1/3 top-0 h-full w-px bg-white/35" />
          <span className="absolute left-2/3 top-0 h-full w-px bg-white/35" />
          <span className="absolute top-1/3 left-0 w-full h-px bg-white/35" />
          <span className="absolute top-2/3 left-0 w-full h-px bg-white/35" />
        </div>
        {HANDLES.map((hd) => (
          <span
            key={hd.key}
            role="presentation"
            onPointerDown={start(hd.key)}
            style={{ cursor: hd.cursor }}
            className={cn(
              'absolute h-4 w-4 rounded-full border-2 border-white bg-accent shadow-card touch-none',
              hd.className,
            )}
          />
        ))}
      </div>
    </div>
  );
}

// ── Small shared bits ───────────────────────────────────────────────────────
function ToolHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div>
      <p className="text-subheadline font-bold text-label">{title}</p>
      <p className="text-caption text-label-tertiary mt-0.5">{hint}</p>
    </div>
  );
}

function SliderGroup({
  title,
  hint,
  keys,
  adj,
  onBegin,
  onChange,
  onEnd,
  onReset,
}: {
  title: string;
  hint: string;
  keys: (keyof Adjustments)[];
  adj: Adjustments;
  onBegin: () => void;
  onChange: (key: keyof Adjustments, value: number) => void;
  onEnd: () => void;
  onReset: (key: keyof Adjustments) => void;
}) {
  return (
    <div className="space-y-4">
      <ToolHeading title={title} hint={hint} />
      <div className="space-y-3.5">
        {keys.map((k) => (
          <Slider
            key={k}
            label={ADJUSTMENT_LABELS[k]}
            value={adj[k]}
            min={ONE_WAY.has(k) ? 0 : -100}
            max={100}
            step={1}
            digits={0}
            onBegin={onBegin}
            onChange={(v) => onChange(k, v)}
            onEnd={onEnd}
            onReset={() => onReset(k)}
          />
        ))}
      </div>
    </div>
  );
}

/** One labelled slider. Dragging is a single undo step: `onBegin` banks the
 *  pre-drag state on pointer/key down, `onEnd` commits it on release. */
function Slider({
  label,
  value,
  min,
  max,
  step,
  digits,
  suffix = '',
  onBegin,
  onChange,
  onEnd,
  onReset,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  digits: number;
  suffix?: string;
  onBegin: () => void;
  onChange: (v: number) => void;
  onEnd: () => void;
  onReset: () => void;
}) {
  const shown = value > 0 ? `+${value.toFixed(digits)}` : value.toFixed(digits).replace('-', '−');
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <label className="text-caption font-semibold text-label">{label}</label>
        <button
          type="button"
          onClick={onReset}
          disabled={value === 0}
          title="Reset"
          className={cn(
            'text-caption tabular-nums rounded px-1.5 focus-ring',
            value === 0
              ? 'text-label-tertiary cursor-default'
              : 'text-accent hover:bg-fill-quaternary',
          )}
        >
          {shown}
          {suffix}
        </button>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onPointerDown={onBegin}
        onPointerUp={onEnd}
        onKeyDown={onBegin}
        onKeyUp={onEnd}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={label}
        className="mt-1.5 w-full h-4 accent-accent cursor-pointer focus-ring rounded"
      />
    </div>
  );
}
