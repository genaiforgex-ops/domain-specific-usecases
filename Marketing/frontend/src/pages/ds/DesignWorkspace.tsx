import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  FileText,
  Sparkles,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  ImagePlus,
  ExternalLink,
  Link2,
  Unlink,
  Check,
  LayoutTemplate,
  Wand2,
  PartyPopper,
  Send,
} from 'lucide-react';
import { Page } from '../../components/layout/Page';
import { Card, Pill, EmptyState } from '../../components/ui/primitives';
import { Button } from '../../components/ui/Button';
import { Sheet } from '../../components/ui/Sheet';
import { CreativeCard } from '../../components/feature/CreativeCard';
import { BannerImageCard } from '../../components/feature/BannerImageCard';
import { BannerTemplateCard } from '../../components/feature/BannerTemplateCard';
import { BannerImageChat } from '../../components/feature/BannerImageChat';
import { ManualImageEditor } from '../../components/feature/ManualImageEditor';
import { ReassignControl } from '../../components/feature/ReassignControl';
import { RejectControl } from '../../components/feature/RejectControl';
import { MagicOverlay, MAGIC_PHRASES } from '../../components/feature/MagicOverlay';
import { SIZE_LABEL } from '../../components/feature/BriefStatusPill';
import { AD_SIZE_LABELS } from '../../lib/adSizes';
import { categoryLabel } from '../../lib/bannerCategories';
import { api, ApiError } from '../../lib/api';
import { sectionsFor } from '../../lib/briefSpec';
import { useApp } from '../../state/AppContext';
import { cn } from '../../lib/cn';
import type {
  Brief,
  BannerImage,
  BannerSize,
  BannerTemplateSummary,
  Creative,
  HeroGuides,
} from '../../lib/types';

type Step = 'creatives' | 'template' | 'images' | 'export' | 'done';

// Briefs authored before the PL banner-category selector existed have no
// category; the Designer treats them as this default family so they still lock
// (rather than showing every template).
const DEFAULT_BANNER_CATEGORY = 'performance';

const STEPS: { key: Step; label: string }[] = [
  { key: 'creatives', label: 'Creatives' },
  { key: 'template', label: 'Template' },
  { key: 'images', label: 'Hero images' },
  { key: 'export', label: 'Export & send' },
  { key: 'done', label: 'Done' },
];

// The Designer's end-to-end banner workspace — a guided, multi-screen flow that
// keeps each stage focused: review the handed-off copy, pick the banner template
// from the category the Product Lead locked, generate and approve hero imagery
// (Nano Banana) for that template, export to Figma, then explicitly send the
// exported design to the Marketing Lead for review. The brief itself stays out of
// the way behind a "View brief" drawer until the Designer asks for it.
export default function DesignWorkspace() {
  const { id } = useParams();
  const briefId = id!;
  const nav = useNavigate();
  const { toast } = useApp();

  const [brief, setBrief] = useState<Brief | null>(null);
  const [creatives, setCreatives] = useState<Creative[] | null>(null);
  const [images, setImages] = useState<BannerImage[] | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [step, setStep] = useState<Step>('creatives');
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false); // batch image (re)generation
  const [regenId, setRegenId] = useState<string | null>(null); // single-card regenerate
  const [uploadId, setUploadId] = useState<string | null>(null); // single-card custom upload
  const [error, setError] = useState<string | null>(null);
  const [briefOpen, setBriefOpen] = useState(false);

  // The Design Studio: one hero image open in either the conversational editor
  // ('ai') or the manual tool bench ('manual'). The Designer can switch between
  // the two without leaving the image.
  const [studio, setStudio] = useState<{ image: BannerImage; mode: 'ai' | 'manual' } | null>(null);
  const [figmaUrl, setFigmaUrl] = useState<string | null>(null);
  const [figma, setFigma] = useState<{ connected: boolean; handle: string | null } | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [fileName, setFileName] = useState('');
  // The banner template to render with (e.g. performance vs WhatsApp/RCS/RPN
  // messaging), the ad sizes it offers, and which of them are ticked.
  const [templates, setTemplates] = useState<BannerTemplateSummary[]>([]);
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [adSizes, setAdSizes] = useState<BannerSize[]>([]);
  const [selectedSizes, setSelectedSizes] = useState<string[]>([]);
  // How the chosen template crops the hero — the Design Studio draws it as crop
  // guides so a face can't be lost to the Story or Square centre-crop.
  const [heroGuides, setHeroGuides] = useState<HeroGuides | null>(null);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  // The Product Lead locked a banner category on the brief; the Designer may only
  // work from templates in that family. Briefs authored before the PL selector
  // existed have no category — treat them as the default "performance" family.
  const briefCategory = brief?.banner_category || DEFAULT_BANNER_CATEGORY;
  const briefLoaded = brief !== null;

  // Load the category's templates — the gallery is DB-driven, so a category holds
  // however many templates have been seeded for it. If it can't load (e.g. none
  // seeded yet), the step says so and the server falls back to the default template.
  useEffect(() => {
    if (!briefLoaded) return;
    let active = true;
    api
      .bannerTemplates(briefCategory)
      .then((list) => active && setTemplates(list))
      .catch(() => active && setTemplates([]));
    return () => {
      active = false;
    };
  }, [briefLoaded, briefCategory]);

  // Which template is highlighted: the one already recorded on the brief (so a
  // reload resumes on it), else the category's default, else its first. Re-picks if
  // the current choice falls out of range.
  const pickedTemplateId = brief?.banner_template_id ?? null;
  useEffect(() => {
    if (templates.length === 0) return;
    setTemplateId((cur) => {
      if (cur && templates.some((t) => t.id === cur)) return cur;
      const onBrief = templates.find((t) => t.id === pickedTemplateId);
      return (onBrief ?? templates.find((t) => t.is_default) ?? templates[0]).id;
    });
  }, [templates, pickedTemplateId]);

  // Load the selected template's ad sizes, ticking all of them by default.
  useEffect(() => {
    if (!templateId) return;
    let active = true;
    api
      .bannerTemplate(templateId)
      .then((tpl) => {
        if (!active) return;
        setAdSizes(tpl.sizes);
        setSelectedSizes(tpl.sizes.map((s) => s.name));
        setHeroGuides(tpl.hero_guides ?? null);
      })
      .catch(() => {
        if (!active) return;
        setAdSizes([]);
        setSelectedSizes([]);
        setHeroGuides(null);
      });
    return () => {
      active = false;
    };
  }, [templateId]);

  const toggleSize = (name: string) =>
    setSelectedSizes((cur) =>
      cur.includes(name) ? cur.filter((n) => n !== name) : [...cur, name],
    );

  // Load everything, then resume at the furthest step the data supports.
  useEffect(() => {
    let active = true;
    Promise.all([
      api.getBrief(briefId),
      api.listCreatives(briefId).catch(() => [] as Creative[]),
      api.bannerImages(briefId).catch(() => [] as BannerImage[]),
    ])
      .then(([b, cs, imgs]) => {
        if (!active) return;
        setBrief(b);
        setCreatives(cs);
        setImages(imgs);
        setFigmaUrl(b.figma_file_url);
        setFileName(b.project_name || b.product_name || `Brief ${b.id} banners`);
        const approved = imgs.length > 0 && imgs.every((i) => i.status === 'approved');
        // The brief leaves the "design" stage only once the Designer explicitly
        // sends the (already Figma-exported) design for Marketing Lead review.
        if (b.stage !== 'design') setStep('done');
        else if (approved) setStep('export');
        else if (imgs.length > 0) setStep('images');
        else setStep('creatives');
      })
      .catch(() => active && setNotFound(true));
    return () => {
      active = false;
    };
  }, [briefId]);

  const allApproved =
    !!images && images.length > 0 && images.every((i) => i.status === 'approved');
  // The brief has left the Designer's hands — the exported design was
  // explicitly sent for Marketing Lead review.
  const sentForReview = brief ? brief.stage !== 'design' : false;

  // Which steps the Designer may jump to (only ones the data already supports).
  const reachable = useMemo<Record<Step, boolean>>(
    () => ({
      creatives: true,
      template: true,
      images: (images?.length ?? 0) > 0,
      export: allApproved,
      done: sentForReview,
    }),
    [images, allApproved, sentForReview],
  );

  // Check the Figma connection whenever the Designer is on the export step — both
  // before the first export and after (the re-export card needs it too). A client
  // guard resolves to "disconnected" if the check is slow, so it never spins forever.
  useEffect(() => {
    if (step !== 'export') return;
    let settled = false;
    const done = (v: { connected: boolean; handle: string | null }) => {
      if (settled) return;
      settled = true;
      if (aliveRef.current) setFigma(v);
    };
    const timer = setTimeout(() => done({ connected: false, handle: null }), 25000);
    api
      .figmaStatus()
      .then((s) => done({ connected: s.connected, handle: s.handle }))
      .catch(() => done({ connected: false, handle: null }))
      .finally(() => clearTimeout(timer));
    return () => clearTimeout(timer);
  }, [step]);

  // Record the highlighted template on the brief, so regeneration, the Figma export
  // and a later reload all resolve to the same one. A no-op when it's already the
  // brief's template (the server keeps the audit trail to real changes).
  const persistTemplate = async () => {
    if (!templateId || templateId === brief?.banner_template_id) return;
    setBrief(await api.selectBannerTemplate(briefId, templateId));
  };

  // Leave the template step without regenerating — the choice is still recorded,
  // since the export renders with it.
  const continueFromTemplate = async () => {
    setBusy(true);
    setError(null);
    try {
      await persistTemplate();
      setStep('images');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not save the template choice.');
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    setBusy(true);
    setGenerating(true);
    setError(null);
    try {
      await persistTemplate(); // the template art-directs the photos — lock it in first
      setImages(await api.generateBannerImages(briefId, templateId ?? undefined));
      setStep('images');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not generate images.');
    } finally {
      setBusy(false);
      setGenerating(false);
    }
  };

  const regenerate = async (imageId: string) => {
    setError(null);
    setRegenId(imageId);
    try {
      const updated = await api.regenerateBannerImage(briefId, imageId, templateId ?? undefined);
      setImages((prev) => (prev ? prev.map((i) => (i.id === imageId ? updated : i)) : prev));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not regenerate image.');
    } finally {
      setRegenId(null);
    }
  };

  const upload = async (imageId: string, file: File) => {
    setError(null);
    setUploadId(imageId);
    try {
      const updated = await api.uploadBannerImage(briefId, imageId, file);
      setImages((prev) => (prev ? prev.map((i) => (i.id === imageId ? updated : i)) : prev));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not upload image.');
    } finally {
      setUploadId(null);
    }
  };

  const approve = async () => {
    setBusy(true);
    setError(null);
    try {
      setImages(await api.approveBannerImages(briefId));
      setStep('export');
      toast('Images approved — ready for Figma', 'success');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not approve images.');
    } finally {
      setBusy(false);
    }
  };

  const connectFigma = async () => {
    setConnecting(true);
    setError(null);
    try {
      const { authorize_url } = await api.figmaConnect();
      window.open(authorize_url, '_blank', 'noopener,noreferrer');
      for (let i = 0; i < 40 && aliveRef.current; i++) {
        await new Promise((r) => setTimeout(r, 2500));
        const s = await api.figmaStatus();
        if (s.connected) {
          if (aliveRef.current) setFigma({ connected: true, handle: s.handle });
          toast('Figma connected', 'success');
          return;
        }
      }
      if (aliveRef.current) setError('Still waiting on Figma. Finish the login tab, then retry.');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start Figma login.');
    } finally {
      if (aliveRef.current) setConnecting(false);
    }
  };

  const disconnectFigma = async () => {
    setError(null);
    try {
      await api.figmaDisconnect();
      if (aliveRef.current) setFigma({ connected: false, handle: null });
      toast('Figma disconnected', 'success');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not disconnect Figma.');
    }
  };

  const exportToFigma = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.figmaExport(
        briefId,
        fileName,
        adSizes.length ? selectedSizes : undefined,
        templateId ?? undefined,
      );
      setFigmaUrl(result.file_url);
      toast(`Exported ${result.creatives} creatives × ${result.sizes} sizes to Figma`, 'success');
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setFigma({ connected: false, handle: null });
      setError(e instanceof ApiError ? e.message : 'Could not export to Figma.');
    } finally {
      setBusy(false);
    }
  };

  const submitForReview = async () => {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.submitDesignForReview(briefId);
      setBrief(updated);
      setStep('done');
      toast('Sent to the Marketing Lead for creative review', 'success');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not send for review.');
    } finally {
      setBusy(false);
    }
  };

  if (notFound) {
    return (
      <Page>
        <EmptyState icon={<FileText size={26} />} title="Asset not found" body="It may have been removed, or it hasn't been handed to design yet." />
        <div className="flex justify-center">
          <Button variant="tinted" onClick={() => nav('/assets')}>Back to My Assets</Button>
        </div>
      </Page>
    );
  }
  if (!brief || creatives === null || images === null) {
    return (
      <Page>
        <div className="flex justify-center py-20">
          <span className="h-7 w-7 rounded-full border-2 border-separator border-t-accent animate-spin" aria-label="Loading" />
        </div>
      </Page>
    );
  }

  const title = brief.project_name || brief.product_name || 'Untitled brief';

  // The creative the open Design Studio image illustrates, and the write-back that
  // keeps the card grid and the studio in step after an edit lands.
  const studioHeadline = studio
    ? creatives.find((c) => c.id === studio.image.creative_id)?.headline ?? 'Creative'
    : '';
  const onStudioUpdate = (img: BannerImage) => {
    setImages((prev) => (prev ? prev.map((i) => (i.id === img.id ? img : i)) : prev));
    setStudio((s) => (s ? { ...s, image: img } : s));
  };

  return (
    <Page>
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <button
          onClick={() => nav('/assets')}
          className="inline-flex items-center gap-1.5 text-footnote text-label-secondary hover:text-label focus-ring rounded px-1"
        >
          <ArrowLeft size={15} /> My Assets
        </button>
        {/* Top-right actions — reassign this brief to another Designer, or send it
            back to the Copywriter. Both open a popup and leave the workspace once
            the brief is no longer the Designer's. */}
        <div className="flex items-center gap-2 flex-wrap">
          {step !== 'done' && (
            <>
              <ReassignControl
                brief={brief}
                onChanged={setBrief}
                onReassigned={() => nav('/assets')}
                size="sm"
              />
              <RejectControl
                brief={brief}
                onChanged={() => nav('/assets')}
                title="Send back to the Copywriter"
                description="If the copies need rework before you can design the banners, send the brief back to the Copywriter with a note."
                placeholder="What do the copies need before design can start?"
                confirmLabel="Send back to Copywriter"
                size="sm"
              />
            </>
          )}
          <Button variant="plain" onClick={() => setBriefOpen(true)}>
            <FileText size={15} /> View brief
          </Button>
        </div>
      </div>

      <div className="mb-1 flex items-center gap-2 flex-wrap">
        <Pill icon={<Wand2 size={11} className="text-accent" />}>Banner production</Pill>
        <Pill>{SIZE_LABEL[brief.brief_type]}</Pill>
      </div>
      <h1 className="text-large-title font-bold tracking-tight text-sheen">{title}</h1>
      <p className="mt-1 mb-4 text-callout text-label-secondary">
        Produce this brief's banner set — pick a template, work the hero images, then export to Figma.
      </p>

      <Stepper step={step} reachable={reachable} onGo={setStep} />

      {error && (
        <p className="flex items-center gap-1.5 text-footnote text-error mt-4" role="alert">
          <AlertCircle size={14} className="shrink-0" /> {error}
        </p>
      )}

      <div className="mt-5">
        {step === 'creatives' && (
          <CreativesStep
            creatives={creatives}
            busy={busy}
            hasImages={images.length > 0}
            onNext={() => setStep('template')}
          />
        )}

        {step === 'template' && (
          <TemplateStep
            templates={templates}
            category={briefCategory}
            templateId={templateId}
            hasImages={images.length > 0}
            // The existing photos were composed for whatever template is on the
            // brief — switching means they no longer match the layout.
            switchedAwayFromImages={images.length > 0 && templateId !== pickedTemplateId}
            busy={busy}
            generating={generating}
            onSelect={setTemplateId}
            onGenerate={generate}
            onContinue={continueFromTemplate}
            onBack={() => setStep('creatives')}
          />
        )}

        {step === 'images' && (
          <ImagesStep
            briefId={briefId}
            images={images}
            creatives={creatives}
            busy={busy}
            generating={generating}
            regenId={regenId}
            uploadId={uploadId}
            allApproved={allApproved}
            onRegenerate={regenerate}
            onEdit={(img) => setStudio({ image: img, mode: 'ai' })}
            onManualEdit={(img) => setStudio({ image: img, mode: 'manual' })}
            onUpload={upload}
            onRegenerateAll={generate}
            onApprove={approve}
            onBack={() => setStep('template')}
            onContinue={() => setStep('export')}
          />
        )}

        {step === 'export' && (
          <ExportStep
            fileName={fileName}
            setFileName={setFileName}
            adSizes={adSizes}
            selectedSizes={selectedSizes}
            onToggleSize={toggleSize}
            figma={figma}
            figmaUrl={figmaUrl}
            connecting={connecting}
            busy={busy}
            onConnect={connectFigma}
            onDisconnect={disconnectFigma}
            onExport={exportToFigma}
            onSubmitReview={submitForReview}
            onBack={() => setStep('images')}
          />
        )}

        {step === 'done' && <DoneStep figmaUrl={figmaUrl} count={creatives.length} onClose={() => nav('/assets')} />}
      </div>

      <Sheet open={briefOpen} onClose={() => setBriefOpen(false)} title="Brief" wide>
        <BriefReadOnly brief={brief} />
      </Sheet>

      {/* Design Studio — the same image, either conversationally or by hand. */}
      <BannerImageChat
        briefId={briefId}
        image={studio?.mode === 'ai' ? studio.image : null}
        headline={studioHeadline}
        onClose={() => setStudio(null)}
        onUpdated={onStudioUpdate}
        onSwitchToManual={() => setStudio((s) => (s ? { ...s, mode: 'manual' } : s))}
      />
      <ManualImageEditor
        briefId={briefId}
        image={studio?.mode === 'manual' ? studio.image : null}
        headline={studioHeadline}
        guides={heroGuides}
        onClose={() => setStudio(null)}
        onUpdated={onStudioUpdate}
        onSwitchToAi={() => setStudio((s) => (s ? { ...s, mode: 'ai' } : s))}
      />
    </Page>
  );
}

// ── Stepper ──────────────────────────────────────────────────────────────────
function Stepper({
  step,
  reachable,
  onGo,
}: {
  step: Step;
  reachable: Record<Step, boolean>;
  onGo: (s: Step) => void;
}) {
  const activeIdx = STEPS.findIndex((s) => s.key === step);
  return (
    <ol className="flex items-center gap-2 sm:gap-3">
      {STEPS.map((s, i) => {
        const done = i < activeIdx;
        const active = i === activeIdx;
        const canGo = reachable[s.key];
        return (
          <li key={s.key} className="flex items-center gap-2 sm:gap-3 min-w-0">
            <button
              disabled={!canGo}
              onClick={() => canGo && onGo(s.key)}
              className={cn(
                'flex items-center gap-2 rounded-full pl-1.5 pr-3 py-1 focus-ring',
                canGo ? 'cursor-pointer' : 'cursor-default',
              )}
            >
              <span
                className={cn(
                  'grid place-items-center h-6 w-6 rounded-full text-caption font-bold shrink-0',
                  active && 'bg-accent text-white',
                  done && 'bg-[color:var(--color-success)] text-white',
                  !active && !done && 'bg-fill-quaternary text-label-tertiary',
                )}
              >
                {done ? <Check size={13} /> : i + 1}
              </span>
              <span
                className={cn(
                  'text-footnote font-semibold whitespace-nowrap',
                  active ? 'text-label' : 'text-label-tertiary',
                )}
              >
                {s.label}
              </span>
            </button>
            {i < STEPS.length - 1 && <span className="h-px w-4 sm:w-8 bg-separator shrink-0" />}
          </li>
        );
      })}
    </ol>
  );
}

// ── Step 1: Creatives ──────────────────────────────────────────────────────
function CreativesStep({
  creatives,
  busy,
  hasImages,
  onNext,
}: {
  creatives: Creative[];
  busy: boolean;
  hasImages: boolean;
  onNext: () => void;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3 mb-1 flex-wrap">
        <div>
          <p className="text-subheadline font-bold text-label">Approved creatives</p>
          <p className="text-caption text-label-tertiary mt-0.5">
            The copy the Strategist handed off. Next, pick the banner template these will be
            produced on{hasImages ? '' : ' — it art-directs the hero images'}.
          </p>
        </div>
        <Button onClick={onNext} disabled={busy}>
          Choose template <ArrowRight size={16} />
        </Button>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-3 mt-4">
        {creatives.map((c, i) => (
          <CreativeCard key={c.id} c={c} index={i} />
        ))}
      </div>
    </Card>
  );
}

// ── Step 2: Hero images ──────────────────────────────────────────────────────
function ImagesStep({
  briefId,
  images,
  creatives,
  busy,
  generating,
  regenId,
  uploadId,
  allApproved,
  onRegenerate,
  onEdit,
  onManualEdit,
  onUpload,
  onRegenerateAll,
  onApprove,
  onBack,
  onContinue,
}: {
  briefId: string;
  images: BannerImage[];
  creatives: Creative[];
  busy: boolean;
  generating: boolean;
  regenId: string | null;
  uploadId: string | null;
  allApproved: boolean;
  onRegenerate: (imageId: string) => void;
  onEdit: (img: BannerImage) => void;
  onManualEdit: (img: BannerImage) => void;
  onUpload: (imageId: string, file: File) => void;
  onRegenerateAll: () => void;
  onApprove: () => void;
  onBack: () => void;
  onContinue: () => void;
}) {
  const headlineFor = (cid: string) => creatives.find((c) => c.id === cid)?.headline ?? 'Creative';
  return (
    <Card className="relative overflow-hidden p-5">
      <AnimatePresence>
        {generating && (
          <MagicOverlay phrases={MAGIC_PHRASES.image} label="Generating hero images" className="rounded-lg" />
        )}
      </AnimatePresence>
      <div className="flex items-center justify-between gap-3 mb-1 flex-wrap">
        <div>
          <p className="text-subheadline font-bold text-label">Review hero images</p>
          <p className="text-caption text-label-tertiary mt-0.5">
            Generated with Nano Banana. Refine one by describing the change, or open the manual
            tools to crop, straighten and tune it by hand — then approve the set.
          </p>
        </div>
        <Button variant="tinted" onClick={onRegenerateAll} disabled={busy}>
          <RefreshCw size={16} /> {busy ? 'Working…' : 'Regenerate all'}
        </Button>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-3 mt-4">
        {images.map((img) => (
          <BannerImageCard
            key={`${img.id}-${img.updated_at}`}
            briefId={briefId}
            img={img}
            headline={headlineFor(img.creative_id)}
            onRegenerate={() => onRegenerate(img.id)}
            onEdit={() => onEdit(img)}
            onManualEdit={() => onManualEdit(img)}
            onUpload={(file) => onUpload(img.id, file)}
            regenerating={regenId === img.id}
            uploading={uploadId === img.id}
            disabled={busy || regenId !== null || uploadId !== null}
          />
        ))}
      </div>

      <div className="mt-5 flex items-center justify-between gap-2">
        <Button variant="plain" onClick={onBack} disabled={busy}>
          <ArrowLeft size={16} /> Back
        </Button>
        {allApproved ? (
          <Button onClick={onContinue} disabled={busy}>
            Continue <ArrowRight size={16} />
          </Button>
        ) : (
          <Button onClick={onApprove} disabled={busy}>
            <CheckCircle2 size={16} /> {busy ? 'Approving…' : 'Approve & continue'}
          </Button>
        )}
      </div>
    </Card>
  );
}

// ── Step 2: Banner template ──────────────────────────────────────────────────
// The gate before any imagery exists. The Designer picks one template from the
// category the Product Lead locked, choosing by its sample artwork; that template
// art-directs the hero photos (where the subject sits, what shape the photo is) and
// later renders the export, so it's decided here and recorded on the brief.
function TemplateStep({
  templates,
  category,
  templateId,
  hasImages,
  switchedAwayFromImages,
  busy,
  generating,
  onSelect,
  onGenerate,
  onContinue,
  onBack,
}: {
  templates: BannerTemplateSummary[];
  category: string;
  templateId: string | null;
  hasImages: boolean;
  switchedAwayFromImages: boolean;
  busy: boolean;
  generating: boolean;
  onSelect: (id: string) => void;
  onGenerate: () => void;
  onContinue: () => void;
  onBack: () => void;
}) {
  const chosen = templates.find((t) => t.id === templateId) ?? null;
  return (
    <Card className="relative overflow-hidden p-5">
      <AnimatePresence>
        {generating && (
          <MagicOverlay phrases={MAGIC_PHRASES.image} label="Generating hero images" className="rounded-lg" />
        )}
      </AnimatePresence>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <p className="text-subheadline font-bold text-label">Pick a banner template</p>
          <p className="text-caption text-label-tertiary mt-0.5 max-w-2xl">
            These are the templates in the category set on the brief. The one you pick sets the
            design and art-directs the hero photos — so choose it before generating images.
          </p>
        </div>
        <Pill icon={<LayoutTemplate size={11} className="text-accent" />}>
          {categoryLabel(category)}
        </Pill>
      </div>

      {templates.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            icon={<LayoutTemplate size={24} />}
            title="No templates in this category yet"
            body="Hero images will be generated on the default template. Ask an Admin to add templates for this category."
          />
        </div>
      ) : (
        <div
          role="radiogroup"
          aria-label="Banner template"
          className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4"
        >
          {templates.map((t) => (
            <BannerTemplateCard
              key={t.id}
              template={t}
              selected={t.id === templateId}
              disabled={busy || generating}
              onSelect={() => onSelect(t.id)}
            />
          ))}
        </div>
      )}

      {chosen && (
        <p className="mt-3 text-caption text-label-secondary">
          Selected: <span className="font-semibold text-label">{chosen.name}</span>
          {chosen.size_names.length > 0 && (
            <> · {chosen.size_names.map((n) => AD_SIZE_LABELS[n] ?? n).join(' · ')}</>
          )}
        </p>
      )}

      {switchedAwayFromImages && (
        <p className="mt-2 flex items-start gap-1.5 text-caption text-label-secondary">
          <AlertCircle size={14} className="shrink-0 mt-px text-accent" />
          Your existing hero images were composed for the previous template. Regenerate them so the
          subjects sit clear of this template's copy area.
        </p>
      )}

      <div className="mt-5 flex items-center justify-between gap-2 flex-wrap">
        <Button variant="plain" onClick={onBack} disabled={busy}>
          <ArrowLeft size={16} /> Back
        </Button>
        <div className="flex items-center gap-2 flex-wrap">
          {hasImages && (
            <Button variant="tinted" onClick={onGenerate} disabled={busy}>
              <RefreshCw size={16} />
              {busy ? 'Regenerating…' : 'Regenerate with this template'}
            </Button>
          )}
          <Button onClick={hasImages ? onContinue : onGenerate} disabled={busy}>
            {hasImages ? (
              <>
                Continue to images <ArrowRight size={16} />
              </>
            ) : (
              <>
                <Sparkles size={16} /> {busy ? 'Generating images…' : 'Generate hero images'}
              </>
            )}
          </Button>
        </div>
      </div>
    </Card>
  );
}

// ── Step 3: Export to Figma, then send for review ────────────────────────────
function ExportStep({
  fileName,
  setFileName,
  adSizes,
  selectedSizes,
  onToggleSize,
  figma,
  figmaUrl,
  connecting,
  busy,
  onConnect,
  onDisconnect,
  onExport,
  onSubmitReview,
  onBack,
}: {
  fileName: string;
  setFileName: (v: string) => void;
  adSizes: BannerSize[];
  selectedSizes: string[];
  onToggleSize: (name: string) => void;
  figma: { connected: boolean; handle: string | null } | null;
  figmaUrl: string | null;
  connecting: boolean;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onExport: () => void;
  onSubmitReview: () => void;
  onBack: () => void;
}) {
  // Block export when the picker is shown but nothing is ticked.
  const noSizes = adSizes.length > 0 && selectedSizes.length === 0;

  // The Figma connection block — shown in both the first-export form and the
  // re-export card, so a re-export can re-authorise if the token has lapsed.
  const connectionGate = (
    <div className="mt-3 flex items-center gap-2 flex-wrap">
      {figma === null ? (
        <span className="flex items-center gap-2 text-caption text-label-tertiary">
          <span className="h-3.5 w-3.5 rounded-full border-2 border-separator border-t-accent animate-spin" />
          Checking Figma connection…
        </span>
      ) : figma.connected ? (
        <>
          <Pill hue="var(--color-success)" icon={<CheckCircle2 size={11} />}>
            Figma connected{figma.handle ? ` · ${figma.handle}` : ''}
          </Pill>
          <button
            type="button"
            onClick={onDisconnect}
            disabled={busy}
            className="inline-flex items-center gap-1 text-caption text-label-tertiary hover:text-label focus-ring rounded-md px-1.5 py-0.5 disabled:opacity-50"
          >
            <Unlink size={13} /> Disconnect
          </button>
        </>
      ) : (
        <>
          <Button variant="tinted" onClick={onConnect} disabled={connecting}>
            <Link2 size={16} /> {connecting ? 'Waiting for Figma…' : 'Connect Figma'}
          </Button>
          <span className="text-caption text-label-tertiary">
            Authorize Figma in the new tab, then this enables automatically.
          </span>
        </>
      )}
    </div>
  );

  // Once exported, the file is there to review — but the Designer can still
  // re-export (e.g. after regenerating a hero image) to push the updated banners
  // to a fresh Figma file, or hand the design to the Marketing Lead.
  if (figmaUrl) {
    return (
      <Card className="p-5 border-l-4 border-l-accent">
        <p className="text-subheadline font-bold text-label">Exported to Figma</p>
        <p className="text-caption text-label-tertiary mt-0.5">
          Review the rendered banners in Figma. Regenerated a hero image since exporting? Re-export
          to push the updated banners into a fresh Figma file. When you're happy, send the design to
          the Marketing Lead for creative review.
        </p>
        <div className="mt-4">
          <a href={figmaUrl} target="_blank" rel="noreferrer" className="focus-ring rounded">
            <Button variant="tinted">
              <ExternalLink size={16} /> Open in Figma
            </Button>
          </a>
        </div>

        {connectionGate}
        {noSizes && (
          <p className="mt-2 text-caption2 text-error">Pick at least one ad size to re-export.</p>
        )}

        <div className="mt-5 flex items-center justify-between gap-2 flex-wrap">
          <Button variant="plain" onClick={onBack} disabled={busy}>
            <ArrowLeft size={16} /> Back
          </Button>
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="tinted"
              onClick={onExport}
              disabled={busy || !figma?.connected || noSizes}
            >
              <ImagePlus size={16} /> {busy ? 'Re-exporting…' : 'Re-export to Figma'}
            </Button>
            <Button onClick={onSubmitReview} disabled={busy}>
              <Send size={16} /> {busy ? 'Sending…' : 'Send for Marketing Lead approval'}
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-5">
      <p className="text-subheadline font-bold text-label">Export to Figma</p>
      <p className="text-caption text-label-tertiary mt-0.5">
        Creates a new Figma file and renders each approved creative across the ad sizes you pick
        below. Exporting is required before the design can be sent for Marketing Lead review.
      </p>

      <label htmlFor="figma-file-name" className="mt-4 block text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">
        Figma file name
      </label>
      <input
        id="figma-file-name"
        value={fileName}
        onChange={(e) => setFileName(e.target.value)}
        maxLength={120}
        placeholder="e.g. Diwali performance creatives"
        className="mt-2 w-full rounded-md border border-separator bg-bg px-3 py-2 text-body text-label focus-ring"
      />

      {/* Ad-size picker — the selected template's formats */}
      {adSizes.length > 0 && (
        <fieldset className="mt-4">
          <legend className="text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">
            Ad sizes to export
          </legend>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
            {adSizes.map((s) => {
              const checked = selectedSizes.includes(s.name);
              return (
                <label
                  key={s.name}
                  className={cn(
                    'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 focus-within:ring-2 focus-within:ring-accent/40',
                    checked ? 'border-accent bg-accent/5' : 'border-separator',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggleSize(s.name)}
                    className="h-4 w-4 accent-accent focus-ring rounded"
                  />
                  <span className="min-w-0">
                    <span className="block text-caption font-semibold text-label">
                      {AD_SIZE_LABELS[s.name] ?? s.name}
                    </span>
                    <span className="block text-caption2 text-label-tertiary tabular-nums">
                      {s.w}×{s.h}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
          {noSizes && (
            <p className="mt-2 text-caption2 text-error">Pick at least one ad size to export.</p>
          )}
        </fieldset>
      )}

      {/* Figma connection gate */}
      {connectionGate}

      <div className="mt-5 flex items-center justify-between gap-2">
        <Button variant="plain" onClick={onBack} disabled={busy}>
          <ArrowLeft size={16} /> Back
        </Button>
        <Button onClick={onExport} disabled={busy || !fileName.trim() || !figma?.connected || noSizes}>
          <ImagePlus size={16} /> {busy ? 'Exporting…' : 'Create file & export to Figma'}
        </Button>
      </div>
    </Card>
  );
}

// ── Step 4: Done ─────────────────────────────────────────────────────────────
function DoneStep({
  figmaUrl,
  count,
  onClose,
}: {
  figmaUrl: string | null;
  count: number;
  onClose: () => void;
}) {
  return (
    <Card className="p-8 text-center flex flex-col items-center">
      <div className="grid place-items-center h-14 w-14 rounded-full bg-[color:color-mix(in_srgb,var(--color-success)_16%,transparent)] text-[color:var(--color-success)] mb-3">
        <PartyPopper size={26} />
      </div>
      {figmaUrl ? (
        <>
          <p className="text-title-2 font-bold text-label">Banners are in Figma — sent for review</p>
          <p className="text-subheadline text-label-secondary mt-1 max-w-md">
            {count} creative{count === 1 ? '' : 's'} were rendered across your selected ad sizes
            into your new Figma file, and the design was sent to the Marketing Lead for creative
            review.
          </p>
        </>
      ) : (
        <>
          <p className="text-title-2 font-bold text-label">Sent for Marketing Lead approval</p>
          <p className="text-subheadline text-label-secondary mt-1 max-w-md">
            The design has been handed to the Marketing Lead for creative review. Once they
            approve, it routes on to the Product Lead for final sign-off.
          </p>
        </>
      )}
      <div className="mt-5 flex items-center gap-2 flex-wrap justify-center">
        {figmaUrl && (
          <a href={figmaUrl} target="_blank" rel="noreferrer" className="focus-ring rounded">
            <Button>
              <ExternalLink size={16} /> Open in Figma
            </Button>
          </a>
        )}
        <Button variant="tinted" onClick={onClose}>
          Back to My Assets
        </Button>
      </div>
    </Card>
  );
}

// ── Brief drawer (on-demand) ─────────────────────────────────────────────────
function BriefReadOnly({ brief }: { brief: Brief }) {
  const sections = sectionsFor(brief.brief_type)
    .map((section) => ({
      title: section.title,
      filled: section.fields.filter((f) => (brief[f.key] ?? '').toString().trim()),
    }))
    .filter((s) => s.filled.length > 0);

  return (
    <div className="space-y-4">
      {sections.map((section) => (
        <div key={section.title}>
          <p className="text-subheadline font-bold text-label mb-2">{section.title}</p>
          <dl className="space-y-3">
            {section.filled.map((f) => (
              <div key={f.key}>
                <dt className="text-caption font-semibold text-label-tertiary uppercase tracking-wide">{f.label}</dt>
                <dd className="text-body text-label whitespace-pre-wrap mt-0.5">{brief[f.key]}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
