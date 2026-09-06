import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Save, AlertCircle, Sparkles, PencilLine, Check } from 'lucide-react';
import { useApp } from '../../state/AppContext';
import { Page, PageHeader } from '../../components/layout/Page';
import { Card } from '../../components/ui/primitives';
import { Button } from '../../components/ui/Button';
import { api, ApiError } from '../../lib/api';
import { AiBriefFiller } from '../../components/feature/AiBriefFiller';
import { BriefReferenceImages } from '../../components/feature/BriefReferenceImages';
import {
  sectionsFor,
  missingRequired,
  SIZE_META,
  autoDates,
  submittableFields,
  type FieldSpec,
} from '../../lib/briefSpec';
import type { BriefForm, BriefSize, BannerTemplateSummary } from '../../lib/types';
import { categoriesFromTemplates } from '../../lib/bannerCategories';
import { cn } from '../../lib/cn';

type Step = 'choose' | 'agent' | 'form';

const inputCls =
  'w-full h-11 px-3.5 rounded-md bg-bg-secondary border text-body text-label placeholder:text-label-tertiary focus-ring transition-shadow duration-fast';
const areaCls =
  'w-full min-h-[88px] p-3.5 rounded-md bg-bg-secondary border text-body text-label placeholder:text-label-tertiary focus-ring resize-y transition-shadow duration-fast';

const asSize = (s?: string): BriefSize | null =>
  s === 'small' || s === 'medium' || s === 'large' ? s : null;

function FieldRow({
  field,
  value,
  invalid,
  flash,
  onChange,
}: Readonly<{
  field: FieldSpec;
  value: string;
  invalid: boolean;
  flash: boolean;
  onChange: (v: string) => void;
}>) {
  const border = cn(
    invalid ? 'border-error' : 'border-separator',
    flash && 'border-accent shadow-[0_0_0_4px_var(--color-accent-soft)]',
  );
  // Prose fields take the whole row whatever the column count is at this width.
  const span = field.kind === 'textarea' ? 'col-span-full' : '';
  return (
    <label className={cn('block', span)}>
      <span className="block mb-1.5 text-footnote font-semibold text-label-secondary">
        {field.label}
        {field.mandatory && <span className="text-error"> *</span>}
        {field.auto && (
          <span className="ml-1.5 align-middle text-caption2 font-semibold uppercase tracking-wide text-label-tertiary">
            Auto
          </span>
        )}
      </span>
      {field.kind === 'textarea' ? (
        <textarea className={cn(areaCls, border)} value={value} placeholder={field.placeholder} onChange={(e) => onChange(e.target.value)} />
      ) : (
        // Automatic fields are shown, not asked for — the server derives them on
        // every save, so an editable input would only promise a change it won't keep.
        <input
          type={field.kind === 'date' ? 'date' : 'text'}
          className={cn(inputCls, border, field.auto && 'bg-fill-quaternary text-label-secondary')}
          value={value}
          placeholder={field.placeholder}
          readOnly={field.auto}
          aria-readonly={field.auto}
          tabIndex={field.auto ? -1 : undefined}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {field.help && <span className="block mt-1 text-caption text-label-tertiary">{field.help}</span>}
    </label>
  );
}

// The banner-category picker (Product Lead, at brief creation). Locks which
// template family the Designer works from downstream. Required before submit.
function CategorySelect({
  categories,
  value,
  invalid,
  onChange,
}: Readonly<{
  categories: ReturnType<typeof categoriesFromTemplates>;
  value: string;
  invalid: boolean;
  onChange: (slug: string) => void;
}>) {
  return (
    <Card className={cn('mb-4 p-5', invalid && 'border-error')}>
      <p className="text-subheadline font-bold text-label">
        Banner category <span className="text-error">*</span>
      </p>
      <p className="text-caption text-label-tertiary mt-0.5 mb-4">
        Which family of banners this brief produces. The Designer picks the exact template within
        it — but only from this category.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3">
        {categories.map((c) => {
          const selected = c.slug === value;
          return (
            <label
              key={c.slug}
              className={cn(
                'flex cursor-pointer items-start gap-2.5 rounded-md border px-3.5 py-3 focus-within:ring-2 focus-within:ring-accent/40',
                selected ? 'border-accent bg-accent/5' : 'border-separator',
              )}
            >
              <input
                type="radio"
                name="banner-category"
                checked={selected}
                onChange={() => onChange(c.slug)}
                className="mt-0.5 h-4 w-4 accent-accent focus-ring"
              />
              <span className="min-w-0">
                <span className="block text-body font-semibold text-label">{c.label}</span>
                {c.blurb && (
                  <span className="block text-caption text-label-tertiary mt-0.5">{c.blurb}</span>
                )}
                <span className="block text-caption2 text-label-tertiary mt-1">
                  {c.count} template{c.count === 1 ? '' : 's'}
                </span>
              </span>
            </label>
          );
        })}
      </div>
      {invalid && <p className="mt-2 text-caption2 text-error">Pick a banner category to submit.</p>}
    </Card>
  );
}

export default function NewBrief() {
  const { id, size: sizeParam } = useParams();
  const editing = Boolean(id);
  const { toast, refreshBriefs, user, role } = useApp();
  const nav = useNavigate();
  // The Marketing Lead edits a brief *during their review* — they didn't author it,
  // so they can't submit it for approval (that's the author's action, and the API
  // refuses it) and "My Briefs" isn't where they came from. Their edit saves and
  // returns to the brief, where the approve / send-back panel is.
  const [reviewing, setReviewing] = useState(false);

  const [size, setSize] = useState<BriefSize | null>(editing ? null : asSize(sizeParam));
  const [step, setStep] = useState<Step>(editing ? 'form' : 'choose');
  const [agentModel, setAgentModel] = useState<string | null>(null);
  const [briefId, setBriefId] = useState<string | null>(id ?? null);
  // A new brief starts with its dates already filled — today, and the expected date
  // three days on. The server re-derives both on save; this is what the author sees.
  const [form, setForm] = useState<BriefForm>(editing ? {} : autoDates());
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flashed, setFlashed] = useState<Set<string>>(new Set());
  // Banner-template gallery — the PL picks one here; it locks the Designer's
  // template downstream (composition + Figma render).
  const [templates, setTemplates] = useState<BannerTemplateSummary[]>([]);

  useEffect(() => {
    let active = true;
    api
      .bannerTemplates()
      .then((list) => active && setTemplates(list))
      .catch(() => active && setTemplates([]));
    return () => {
      active = false;
    };
  }, []);

  // Create mode reached without a valid size — send back to the picker.
  useEffect(() => {
    if (!editing && !asSize(sizeParam)) nav('/briefs/new', { replace: true });
  }, [editing, sizeParam, nav]);

  // The author owns the brief — default the Owner field to the signed-in user on a
  // new brief. Only fills it when blank, so agent extraction or a manual edit wins.
  useEffect(() => {
    if (editing || !user?.full_name) return;
    setForm((f) => (f.owner_name?.trim() ? f : { ...f, owner_name: user.full_name }));
  }, [editing, user?.full_name]);

  // Edit mode — load the existing brief and lock its type.
  useEffect(() => {
    if (!editing) return;
    api
      .getBrief(id!)
      .then((b) => {
        // Mirrors the API's own rule (briefs._can_edit): the author edits a draft or
        // a returned brief; the assigned Marketing Lead edits while it sits in brief
        // review. Anyone else — or any other stage — is read-only.
        const asAuthor =
          b.creator_id === user?.id &&
          (b.status === 'draft' || b.status === 'changes_requested');
        const asReviewer =
          role === 'ML' && b.stage === 'brief_review' && b.marketing_id === user?.id;
        if (!asAuthor && !asReviewer) {
          nav(`/briefs/${b.id}`, { replace: true });
          return;
        }
        setReviewing(!asAuthor);
        setSize(b.brief_type);
        const { id: _i, status: _s, brief_type: _t, ...rest } = b;
        const fields: BriefForm = {};
        for (const [k, v] of Object.entries(rest)) if (typeof v === 'string') fields[k as keyof BriefForm] = v;
        // Automatic dates: keep the brief's own date, and show the expected date it
        // implies. A brief raised before these were automatic has neither.
        const dates = autoDates(fields.brief_date);
        setForm({ ...fields, ...dates });
      })
      .catch(() => {
        toast('Could not load that brief', 'error');
        nav('/briefs');
      });
  }, [editing, id, nav, toast, role, user?.id]);

  const set = (key: keyof BriefForm, v: string) => setForm((f) => ({ ...f, [key]: v }));

  // The agent drafted values — merge, reveal the form, briefly highlight changes.
  const onAgentFill = (values: BriefForm, model: string, count: number) => {
    setForm((f) => ({ ...f, ...values }));
    setAgentModel(model);
    setStep('form');
    setFlashed(new Set(Object.keys(values)));
    setTimeout(() => setFlashed(new Set()), 2000);
    const filled = count ? `Agent filled ${count} field${count > 1 ? 's' : ''} · ${model}` : 'Agent found nothing to fill — type it in below';
    toast(filled, count ? 'success' : 'default');
  };

  const missing = size ? missingRequired(size, form) : [];
  const missingKeys = new Set(missing.map((m) => m.key));
  // The PL must pick a banner category (the template family the Designer works
  // from) — required, but only enforced on submit like the other required fields.
  const categories = categoriesFromTemplates(templates);
  const categoryMissing = categories.length > 0 && !form.banner_category;

  const persist = async (): Promise<string | null> => {
    if (!size) return null;
    // The dates are the server's to set — send everything else, then show what it
    // actually stamped so the form never disagrees with the brief.
    const content = submittableFields(form);
    const saved = briefId
      ? await api.updateBrief(briefId, content)
      : await api.createBrief(size, content);
    setBriefId(saved.id);
    setForm((f) => ({ ...f, ...autoDates(saved.brief_date) }));
    return saved.id;
  };

  // Where an edit ends: the reviewer goes back to the brief they were reviewing,
  // the author to their list of briefs.
  const exitTo = reviewing ? `/briefs/${id}` : '/briefs';

  const saveDraft = async () => {
    setBusy(true);
    setError(null);
    try {
      await persist();
      refreshBriefs();
      toast(reviewing ? 'Brief updated' : 'Draft saved', 'success');
      nav(exitTo);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : `Could not save the ${reviewing ? 'brief' : 'draft'}.`,
      );
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    setTried(true);
    if (categoryMissing) {
      setError('Pick a banner category before submitting.');
      return;
    }
    if (missing.length) {
      setError(`Complete the ${missing.length} required field${missing.length > 1 ? 's' : ''} marked in red.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const savedId = await persist();
      if (savedId == null) return;
      await api.submitBrief(savedId);
      refreshBriefs();
      toast('Brief submitted for approval', 'success');
      nav(`/briefs/${savedId}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not submit the brief.');
    } finally {
      setBusy(false);
    }
  };

  if (!size) return null; // redirecting (invalid size) or loading the brief to edit

  const back = () => {
    if (editing) nav(exitTo);
    else if (step === 'choose') nav('/briefs/new');
    else setStep('choose');
  };
  let backLabel = 'Back';
  if (reviewing) backLabel = 'Back to brief';
  else if (editing) backLabel = 'My Briefs';
  else if (step === 'choose') backLabel = 'Change size';

  return (
    <Page>
      <button
        onClick={back}
        className="inline-flex items-center gap-1.5 text-footnote text-label-secondary hover:text-label mb-3 focus-ring rounded px-1"
      >
        <ArrowLeft size={15} /> {backLabel}
      </button>

      {/* ── Step: choose how to fill ───────────────────────────────────────── */}
      {step === 'choose' && (
        <>
          <PageHeader eyebrow={`${SIZE_META[size].label} brief`} title="How do you want to fill it?" subtitle="Let the agent draft it from your notes, or fill the template yourself." />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <button
              onClick={() => setStep('agent')}
              className="group relative text-left rounded-2xl p-[1.5px] focus-ring overflow-hidden"
              style={{ background: 'linear-gradient(120deg, var(--color-accent), #af52de, #0a84ff)' }}
            >
              <span className="block rounded-2xl bg-bg-tertiary p-6 min-h-[180px] flex flex-col">
                <span className="grid place-items-center h-14 w-14 rounded-xl text-white mb-4" style={{ background: 'linear-gradient(135deg, var(--color-accent), #af52de)' }}>
                  <Sparkles size={26} />
                </span>
                <span className="text-title-3 font-bold text-label">Use the AI agent</span>
                <span className="mt-1 text-subheadline text-label-secondary flex-1">Paste raw notes and the Brief Creator Agent drafts the form for you to review.</span>
                <span className="mt-4 inline-flex items-center gap-1.5 text-footnote font-semibold text-accent">Draft with AI <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" /></span>
              </span>
            </button>

            <button
              onClick={() => setStep('form')}
              className="group text-left rounded-2xl border border-separator bg-bg-tertiary p-6 min-h-[180px] flex flex-col hover:shadow-elevated transition-shadow focus-ring"
            >
              <span className="grid place-items-center h-14 w-14 rounded-xl bg-bg-secondary text-label-secondary group-hover:text-accent mb-4">
                <PencilLine size={26} />
              </span>
              <span className="text-title-3 font-bold text-label">Fill it manually</span>
              <span className="mt-1 text-subheadline text-label-secondary flex-1">Go straight to the template and type each field in yourself.</span>
              <span className="mt-4 inline-flex items-center gap-1.5 text-footnote font-semibold text-accent">Open the form <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" /></span>
            </button>
          </div>
        </>
      )}

      {/* ── Step: AI agent input ───────────────────────────────────────────── */}
      {step === 'agent' && (
        <>
          <PageHeader eyebrow={`${SIZE_META[size].label} brief`} title="Draft with the agent" subtitle="Drop in whatever you have — you'll review and edit everything next." />
          <AiBriefFiller size={size} onFilled={onAgentFill} />
        </>
      )}

      {/* ── Step: the form (manual, or reviewing the agent's draft) ─────────── */}
      {step === 'form' && (
        <>
          <PageHeader
            eyebrow={`${SIZE_META[size].label} brief`}
            title={editing ? 'Edit Brief' : 'Review & complete'}
            subtitle={
              reviewing
                ? 'Correct anything that needs it while you review, then save your changes.'
                : 'Check every field, then save a draft or send it for approval.'
            }
          />

          {agentModel ? (
            <div className="mb-4 flex items-center gap-2.5 rounded-lg border border-separator bg-[color:var(--color-accent-soft)] px-4 py-3">
              <Sparkles size={16} className="text-accent shrink-0" />
              <p className="text-footnote text-label-secondary">
                Drafted by the Brief Creator Agent (<span className="font-mono">{agentModel}</span>). Review the highlighted fields before submitting.
              </p>
            </div>
          ) : (
            !editing && (
              <button
                onClick={() => setStep('agent')}
                className="mb-4 inline-flex items-center gap-1.5 text-footnote font-semibold text-accent hover:underline focus-ring rounded px-1"
              >
                <Sparkles size={14} /> Draft with the AI agent instead
              </button>
            )
          )}

          {categories.length > 0 && (
            <CategorySelect
              categories={categories}
              value={form.banner_category ?? ''}
              invalid={tried && categoryMissing}
              onChange={(slug) => set('banner_category', slug)}
            />
          )}

          <div className="space-y-4">
            {sectionsFor(size).map((section) => (
              <Card key={section.title} className="p-5">
                <p className="text-subheadline font-bold text-label mb-4">{section.title}</p>
                <div className="grid sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
                  {section.fields.map((f) => (
                    <FieldRow
                      key={f.key}
                      field={f}
                      value={form[f.key] ?? ''}
                      invalid={tried && missingKeys.has(f.key)}
                      flash={flashed.has(f.key)}
                      onChange={(v) => set(f.key, v)}
                    />
                  ))}
                </div>
              </Card>
            ))}

            <Card className="p-5">
              <p className="text-subheadline font-bold text-label mb-1">
                Samples / Examples / References
              </p>
              <BriefReferenceImages
                briefId={briefId}
                ensureBriefId={persist}
                onToast={toast}
              />
            </Card>
          </div>

          {error && (
            <p className="flex items-center gap-1.5 text-footnote text-error mt-4" role="alert">
              <AlertCircle size={14} className="shrink-0" /> {error}
            </p>
          )}

          <div className="flex flex-wrap justify-end gap-2 mt-5">
            <Button variant="plain" onClick={() => nav(exitTo)} disabled={busy}>Cancel</Button>
            {reviewing ? (
              // A reviewer's edit is already in the pipeline — it is saved, not
              // submitted; they approve or send it back on the brief itself.
              <Button onClick={saveDraft} disabled={busy}><Save size={16} /> Save changes</Button>
            ) : (
              <>
                <Button variant="tinted" onClick={saveDraft} disabled={busy}><Save size={16} /> Save draft</Button>
                <Button onClick={submit} disabled={busy}>Submit for approval <ArrowRight size={16} /></Button>
              </>
            )}
          </div>
          <p className="mt-2 text-caption text-label-tertiary text-right flex items-center justify-end gap-1">
            {reviewing ? (
              <>Saved changes go straight to the brief — approve or send it back there.</>
            ) : (
              <>
                <Check size={12} /> <span className="text-error">*</span> required before submitting
              </>
            )}
          </p>
        </>
      )}
    </Page>
  );
}
