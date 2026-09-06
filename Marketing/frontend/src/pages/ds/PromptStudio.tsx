import { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  FileText,
  Image as ImageIcon,
  PenLine,
  RotateCcw,
  Save,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-react';
import { Page } from '../../components/layout/Page';
import { Card, Pill, EmptyState } from '../../components/ui/primitives';
import { Button } from '../../components/ui/Button';
import { api, ApiError } from '../../lib/api';
import { useApp } from '../../state/AppContext';
import { cn } from '../../lib/cn';
import type { AgentPrompt, DesignPrompt, ImagePrompt } from '../../lib/types';

// Friendly names for the ad formats each image template renders.
const SIZE_LABELS: Record<string, string> = {
  square: 'Square',
  story: 'Story',
  portrait: 'Portrait',
  landscape: 'Landscape',
  link: 'Link / Feed',
  WA: 'WhatsApp',
  RCS: 'RCS',
  RPN: 'Rich Push',
};

// Matches app.adk.agents.AGENT_KIND_CREATIVE — the copy agent.
const AGENT_KIND_CREATIVE = 'creative';

const AGENT_ICON: Record<string, typeof FileText> = {
  brief_creator: FileText,
  [AGENT_KIND_CREATIVE]: PenLine,
};

// Shared styles so every node + editor looks identical.
const TEXTAREA_CLASS =
  'mt-2 w-full rounded-md border border-separator bg-bg px-3 py-2 text-footnote text-label focus-ring resize-y disabled:opacity-60';
const LABEL_CLASS =
  'mt-4 block text-caption2 font-semibold text-label-tertiary uppercase tracking-wide';

type Selection =
  | { type: 'agent'; kind: string }
  | { type: 'design' }
  | { type: 'image'; templateId: string };

// The Prompt Studio — the AI prompts for the work *your role* does. The pipeline
// graph sits on the left; the prompt editor for the selected node fills the right.
// Everything is saved per-user, so edits change only how your own runs behave.
export default function PromptStudio() {
  const { toast, role } = useApp();
  const showDesign = role === 'DS';

  const [agents, setAgents] = useState<AgentPrompt[] | null>(null);
  const [images, setImages] = useState<ImagePrompt[] | null>(null);
  const [design, setDesign] = useState<DesignPrompt | null>(null);
  const [sel, setSel] = useState<Selection | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const jobs: [Promise<AgentPrompt[]>, Promise<ImagePrompt[]>, Promise<DesignPrompt | null>] = [
      api.agentPrompts(),
      showDesign ? api.imagePrompts() : Promise.resolve([]),
      showDesign ? api.designPrompt() : Promise.resolve(null),
    ];
    Promise.all(jobs)
      .then(([a, i, d]) => {
        setAgents(a);
        setImages(i);
        setDesign(d);
        setSel((cur) => cur ?? (showDesign ? { type: 'design' } : a[0] ? { type: 'agent', kind: a[0].kind } : null));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load prompts.'));
  }, [showDesign]);

  const loading = agents === null || images === null;
  const empty = !loading && agents.length === 0 && !showDesign;

  return (
    <Page>
      <div className="mb-1 flex items-center gap-2 flex-wrap">
        <Pill icon={<SlidersHorizontal size={11} className="text-accent" />}>Context Studio</Pill>
      </div>
      <h1 className="text-large-title font-bold tracking-tight mb-1 text-sheen">
        {showDesign ? 'Design prompts' : 'Agent prompts'}
      </h1>
      <p className="mt-1 text-callout text-label-secondary mb-5 max-w-3xl">
        {showDesign
          ? 'How your hero images are generated, as a graph. Pick a node on the left — the Design prompt is the shared base; each format (performance statics, social media) adds its own art-direction on top. Edits are saved to your account.'
          : 'The AI prompt for the work you do. Pick the node on the left; your instruction is appended to the agent’s brand base prompt and saved to your account.'}
      </p>

      {error && (
        <p className="flex items-center gap-1.5 text-footnote text-error mb-4" role="alert">
          <AlertCircle size={14} className="shrink-0" /> {error}
        </p>
      )}

      {loading ? (
        <div className="flex justify-center py-20">
          <span
            className="h-7 w-7 rounded-full border-2 border-separator border-t-accent animate-spin"
            aria-label="Loading"
          />
        </div>
      ) : empty ? (
        <EmptyState
          icon={<Sparkles size={26} />}
          title="No prompts for your role"
          body="Prompt configuration appears here for the roles that run an AI agent."
        />
      ) : (
        <div className="lg:grid lg:grid-cols-[340px_minmax(0,1fr)] lg:gap-6 lg:items-start">
          <div className="mb-4 lg:mb-0 lg:sticky lg:top-4">
            <PromptGraph
              agents={agents!}
              images={images!}
              design={design}
              showDesign={showDesign}
              sel={sel}
              onSelect={setSel}
            />
          </div>
          <NodeEditor
            sel={sel}
            agents={agents!}
            images={images!}
            design={design}
            onSavedAgent={(a) =>
              setAgents((cur) => (cur ? cur.map((x) => (x.kind === a.kind ? a : x)) : cur))
            }
            onSavedImage={(i) =>
              setImages((cur) =>
                cur ? cur.map((x) => (x.template_id === i.template_id ? i : x)) : cur,
              )
            }
            onSavedDesign={setDesign}
            onError={setError}
            onToast={toast}
          />
        </div>
      )}
    </Page>
  );
}

// ── The graph (left rail): a vertical flow of uniform node cards ──────────────
function PromptGraph({
  agents,
  images,
  design,
  showDesign,
  sel,
  onSelect,
}: {
  agents: AgentPrompt[];
  images: ImagePrompt[];
  design: DesignPrompt | null;
  showDesign: boolean;
  sel: Selection | null;
  onSelect: (s: Selection) => void;
}) {
  return (
    <div className="rounded-xl border border-separator bg-bg-secondary/40 p-3">
      <div className="flex flex-col">
        {agents.map((a, idx) => {
          const Ico = AGENT_ICON[a.kind] ?? Sparkles;
          return (
            <div key={a.kind}>
              {idx > 0 && <Connector />}
              <NodeCard
                icon={Ico}
                title={a.name}
                meta={`${a.role} · ${a.output_label}`}
                custom={a.is_custom}
                enabled={a.enabled}
                selected={sel?.type === 'agent' && sel.kind === a.kind}
                onClick={() => onSelect({ type: 'agent', kind: a.kind })}
              />
            </div>
          );
        })}

        {showDesign && (
          <>
            {agents.length > 0 && <Connector />}
            <NodeCard
              icon={ImageIcon}
              title="Design prompt"
              meta="Shared base · Nano Banana"
              custom={!!design?.is_custom}
              enabled={!!design?.enabled}
              selected={sel?.type === 'design'}
              onClick={() => onSelect({ type: 'design' })}
            />
            {/* Branch: the per-format additions that build on the design base. */}
            <div className="mt-2 ml-4 border-l-2 border-separator pl-3 flex flex-col gap-2">
              <span className="text-caption2 font-semibold text-label-tertiary uppercase tracking-wide">
                ＋ per format
              </span>
              {images.map((i) => (
                <NodeCard
                  key={i.template_id}
                  icon={ChevronRight}
                  title={i.template_name}
                  meta={i.size_names.map((n) => SIZE_LABELS[n] ?? n).join(' · ')}
                  custom={i.is_custom}
                  enabled={i.enabled}
                  selected={sel?.type === 'image' && sel.templateId === i.template_id}
                  onClick={() => onSelect({ type: 'image', templateId: i.template_id })}
                />
              ))}
              {images.length === 0 && (
                <span className="text-caption2 text-label-tertiary">No formats yet</span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Connector() {
  return (
    <div className="flex justify-center py-1" aria-hidden>
      <ChevronDown size={16} className="text-label-tertiary" />
    </div>
  );
}

function StateBadge({ custom, enabled }: { custom: boolean; enabled: boolean }) {
  return custom && enabled ? <Pill hue="var(--color-accent)">Custom</Pill> : <Pill>Default</Pill>;
}

// One uniform node card — used for every node so the graph reads as one system.
function NodeCard({
  icon: Ico,
  title,
  meta,
  custom,
  enabled,
  selected,
  onClick,
}: {
  icon: typeof FileText;
  title: string;
  meta: string;
  custom: boolean;
  enabled: boolean;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full text-left rounded-lg border bg-bg px-3 py-2.5 flex items-center gap-3 transition-shadow focus-ring',
        selected ? 'border-accent ring-2 ring-accent/30' : 'border-separator hover:border-label-quaternary',
      )}
    >
      <span className="grid place-items-center h-8 w-8 rounded-full bg-fill-quaternary text-label-secondary shrink-0">
        <Ico size={16} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-caption font-bold text-label truncate">{title}</span>
        <span className="block text-caption2 text-label-tertiary truncate">{meta}</span>
      </span>
      <span className="shrink-0">
        <StateBadge custom={custom} enabled={enabled} />
      </span>
    </button>
  );
}

// ── Editor dispatch (right column) ───────────────────────────────────────────
function NodeEditor({
  sel,
  agents,
  images,
  design,
  onSavedAgent,
  onSavedImage,
  onSavedDesign,
  onError,
  onToast,
}: {
  sel: Selection | null;
  agents: AgentPrompt[];
  images: ImagePrompt[];
  design: DesignPrompt | null;
  onSavedAgent: (a: AgentPrompt) => void;
  onSavedImage: (i: ImagePrompt) => void;
  onSavedDesign: (d: DesignPrompt) => void;
  onError: (msg: string | null) => void;
  onToast: (msg: string, kind?: 'success' | 'error') => void;
}) {
  if (!sel) return null;
  if (sel.type === 'design') {
    if (!design) return null;
    return <DesignEditor design={design} onSaved={onSavedDesign} onError={onError} onToast={onToast} />;
  }
  if (sel.type === 'agent') {
    const agent = agents.find((a) => a.kind === sel.kind);
    if (!agent) return null;
    return <AgentEditor key={agent.kind} agent={agent} onSaved={onSavedAgent} onError={onError} onToast={onToast} />;
  }
  const img = images.find((i) => i.template_id === sel.templateId);
  if (!img) return null;
  return <ImageEditor key={img.template_id} item={img} onSaved={onSavedImage} onError={onError} onToast={onToast} />;
}

// Shared editor chrome so every prompt window is identical.
function EditorShell({
  icon: Ico,
  title,
  badge,
  meta,
  description,
  children,
  onReset,
  resetDisabled,
  resetLabel,
  onSave,
  saveDisabled,
  busy,
}: {
  icon: typeof FileText;
  title: string;
  badge: React.ReactNode;
  meta?: React.ReactNode;
  description: string;
  children: React.ReactNode;
  onReset: () => void;
  resetDisabled: boolean;
  resetLabel: string;
  onSave: () => void;
  saveDisabled: boolean;
  busy: boolean;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="grid place-items-center h-8 w-8 rounded-full bg-fill-quaternary text-label-secondary shrink-0">
          <Ico size={16} />
        </span>
        <p className="text-subheadline font-bold text-label">{title}</p>
        {badge}
        {meta}
      </div>
      <p className="text-caption text-label-tertiary mt-1">{description}</p>
      {children}
      <div className="mt-3 flex items-center justify-between gap-2 flex-wrap">
        <button
          type="button"
          onClick={onReset}
          disabled={resetDisabled}
          className="inline-flex items-center gap-1.5 text-caption text-label-tertiary hover:text-label focus-ring rounded-md px-1.5 py-0.5 disabled:opacity-40"
        >
          <RotateCcw size={13} /> {resetLabel}
        </button>
        <Button onClick={onSave} disabled={saveDisabled}>
          <Save size={16} /> {busy ? 'Saving…' : 'Save prompt'}
        </Button>
      </div>
    </Card>
  );
}

function DesignEditor({
  design,
  onSaved,
  onError,
  onToast,
}: {
  design: DesignPrompt;
  onSaved: (d: DesignPrompt) => void;
  onError: (msg: string | null) => void;
  onToast: (msg: string, kind?: 'success' | 'error') => void;
}) {
  const [text, setText] = useState(design.prompt);
  const [busy, setBusy] = useState(false);
  useEffect(() => setText(design.prompt), [design.prompt]);

  const dirty = text.trim() !== design.prompt.trim();
  const save = async () => {
    setBusy(true);
    onError(null);
    try {
      onSaved(await api.setDesignPrompt(text.trim(), true));
      onToast('Saved your design prompt', 'success');
    } catch (e) {
      onError(e instanceof ApiError ? e.message : 'Could not save the design prompt.');
    } finally {
      setBusy(false);
    }
  };
  const reset = async () => {
    setBusy(true);
    onError(null);
    try {
      onSaved(await api.resetDesignPrompt());
      onToast('Reset the design prompt to the default', 'success');
    } catch (e) {
      onError(e instanceof ApiError ? e.message : 'Could not reset the design prompt.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <EditorShell
      icon={ImageIcon}
      title="Design prompt (shared base)"
      badge={<StateBadge custom={design.is_custom} enabled={design.enabled} />}
      description="The base for every hero image — photography style, quality bar and constraints. Your edits apply to all formats; each creative’s scene and the per-format art-direction are added on top automatically. Tip: keep a “no text, full-bleed” instruction so copy can overlay cleanly."
      onReset={reset}
      resetDisabled={busy || !design.is_custom}
      resetLabel="Reset to default"
      onSave={save}
      saveDisabled={busy || !dirty || text.trim().length === 0}
      busy={busy}
    >
      <label htmlFor="design-base" className={LABEL_CLASS}>Design prompt</label>
      <textarea
        id="design-base"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={16}
        maxLength={8000}
        disabled={busy}
        className={TEXTAREA_CLASS}
      />
    </EditorShell>
  );
}

function AgentEditor({
  agent,
  onSaved,
  onError,
  onToast,
}: {
  agent: AgentPrompt;
  onSaved: (a: AgentPrompt) => void;
  onError: (msg: string | null) => void;
  onToast: (msg: string, kind?: 'success' | 'error') => void;
}) {
  const [text, setText] = useState(agent.append);
  const [busy, setBusy] = useState(false);
  const [showBase, setShowBase] = useState(false);
  useEffect(() => setText(agent.append), [agent.append]);

  const dirty = text.trim() !== agent.append.trim();
  const save = async () => {
    setBusy(true);
    onError(null);
    try {
      onSaved(await api.setAgentPrompt(agent.kind, text.trim(), true));
      onToast(`Saved your prompt for ${agent.name}`, 'success');
    } catch (e) {
      onError(e instanceof ApiError ? e.message : 'Could not save the prompt.');
    } finally {
      setBusy(false);
    }
  };
  const reset = async () => {
    setBusy(true);
    onError(null);
    try {
      onSaved(await api.resetAgentPrompt(agent.kind));
      onToast(`Reset ${agent.name} to the base prompt`, 'success');
    } catch (e) {
      onError(e instanceof ApiError ? e.message : 'Could not reset the prompt.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <EditorShell
      icon={AGENT_ICON[agent.kind] ?? Sparkles}
      title={agent.name}
      badge={<StateBadge custom={agent.is_custom} enabled={agent.enabled} />}
      meta={<span className="text-caption text-label-tertiary">→ {agent.output_label}</span>}
      description={agent.description}
      onReset={reset}
      resetDisabled={busy || !agent.is_custom}
      resetLabel="Reset to base"
      onSave={save}
      saveDisabled={busy || !dirty || text.trim().length === 0}
      busy={busy}
    >
      <button
        type="button"
        onClick={() => setShowBase((v) => !v)}
        className="mt-3 inline-flex items-center gap-1 text-caption font-semibold text-accent focus-ring rounded"
      >
        <ChevronRight size={13} className={cn('transition-transform', showBase && 'rotate-90')} />
        {showBase ? 'Hide' : 'Show'} base prompt (read-only)
      </button>
      {showBase && (
        <pre className="mt-2 max-h-56 overflow-auto rounded-md border border-separator bg-bg-secondary/50 p-3 text-caption2 text-label-secondary whitespace-pre-wrap font-mono">
          {agent.base_prompt}
        </pre>
      )}

      <label htmlFor={`agent-${agent.kind}`} className={LABEL_CLASS}>
        Your instruction — appended to the base prompt
      </label>
      {agent.kind === AGENT_KIND_CREATIVE && (
        <p className="mt-1 text-caption2 text-label-tertiary">
          This is the master level — it applies to every brief. To steer a single brief,
          set its <span className="font-semibold">Copy direction</span> on that brief’s
          Copies tab; it’s read after this one.
        </p>
      )}
      <textarea
        id={`agent-${agent.kind}`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={8}
        maxLength={6000}
        disabled={busy}
        placeholder="e.g. Always weave in a festive Diwali angle and prefer shorter headlines."
        className={TEXTAREA_CLASS}
      />
    </EditorShell>
  );
}

function ImageEditor({
  item,
  onSaved,
  onError,
  onToast,
}: {
  item: ImagePrompt;
  onSaved: (i: ImagePrompt) => void;
  onError: (msg: string | null) => void;
  onToast: (msg: string, kind?: 'success' | 'error') => void;
}) {
  const [text, setText] = useState(item.prompt);
  const [busy, setBusy] = useState(false);
  const formats = useMemo(
    () => item.size_names.map((n) => SIZE_LABELS[n] ?? n).join(' · '),
    [item.size_names],
  );
  useEffect(() => setText(item.prompt), [item.prompt]);

  const dirty = text.trim() !== item.prompt.trim();
  const save = async () => {
    setBusy(true);
    onError(null);
    try {
      onSaved(await api.setImagePrompt(item.template_id, text.trim(), true));
      onToast(`Saved your prompt for ${item.template_name}`, 'success');
    } catch (e) {
      onError(e instanceof ApiError ? e.message : 'Could not save the prompt.');
    } finally {
      setBusy(false);
    }
  };
  const reset = async () => {
    setBusy(true);
    onError(null);
    try {
      onSaved(await api.resetImagePrompt(item.template_id));
      onToast(`Reset ${item.template_name} to the default prompt`, 'success');
    } catch (e) {
      onError(e instanceof ApiError ? e.message : 'Could not reset the prompt.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <EditorShell
      icon={ImageIcon}
      title={item.template_name}
      badge={<StateBadge custom={item.is_custom} enabled={item.enabled} />}
      meta={
        <>
          <Pill>{formats}</Pill>
          <Pill>
            Output {item.image_aspect || 'default'}
            {item.image_size ? ` · ${item.image_size}` : ''}
          </Pill>
        </>
      }
      description="Hero-photo art direction for this format — how the subject is composed and which side is left clear for copy. It’s added on top of the shared Design prompt; the brand rules, quality bar and text-free constraints always apply. The output shape is set as a real image-model parameter (not the prompt)."
      onReset={reset}
      resetDisabled={busy || !item.is_custom}
      resetLabel="Reset to default"
      onSave={save}
      saveDisabled={busy || !dirty || text.trim().length === 0}
      busy={busy}
    >
      <label htmlFor={`image-${item.template_id}`} className={LABEL_CLASS}>Art direction</label>
      <textarea
        id={`image-${item.template_id}`}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={8}
        maxLength={4000}
        disabled={busy}
        placeholder="Describe where the subject sits and which side to leave clear for copy…"
        className={TEXTAREA_CLASS}
      />
    </EditorShell>
  );
}
