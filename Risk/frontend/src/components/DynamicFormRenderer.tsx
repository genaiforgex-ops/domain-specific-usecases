import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, FormField, Input, Select, Textarea } from "./ui";
import type { FormFieldDef, FormSectionDef, FormTemplateSchema } from "../api/client";

export type FormAnswers = Record<string, string | Record<string, string>[]>;

/** Above this, or across more than one line, guidance collapses behind a toggle
 *  so a 38-question form doesn't become a wall of text. */
const INLINE_HINT_MAX = 120;

interface Props {
  schema: FormTemplateSchema;
  answers: FormAnswers;
  onChange: (answers: FormAnswers) => void;
  onSubmit?: () => void;
  readOnly?: boolean;
  submitting?: boolean;
  branded?: boolean;
  /** Field ids the server rejected as missing on the last submit attempt. */
  invalidFieldIds?: string[];
}

function isAnswered(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

function collectFields(schema: FormTemplateSchema): FormFieldDef[] {
  const fields: FormFieldDef[] = [];
  for (const section of schema.sections ?? []) {
    fields.push(...section.fields);
  }
  for (const group of schema.repeatable_groups ?? []) {
    fields.push(...group.fields);
  }
  return fields;
}

function sectionComplete(section: FormSectionDef, answers: FormAnswers): boolean {
  return section.fields
    .filter((f) => f.required)
    .every((f) => isAnswered(answers[f.id]));
}

function sectionProgress(section: FormSectionDef, answers: FormAnswers) {
  const required = section.fields.filter((f) => f.required);
  const done = required.filter((f) => isAnswered(answers[f.id])).length;
  return { done, total: required.length };
}

/** Every unanswered required field, with the section index needed to jump to it. */
export function findMissingRequired(schema: FormTemplateSchema, answers: FormAnswers) {
  const missing: { field: FormFieldDef; sectionIdx: number; sectionTitle: string }[] = [];
  (schema.sections ?? []).forEach((section, sectionIdx) => {
    for (const field of section.fields) {
      if (field.required && !isAnswered(answers[field.id])) {
        missing.push({ field, sectionIdx, sectionTitle: section.title });
      }
    }
  });
  return missing;
}

/** Short guidance reads inline; long guidance (or anything multi-line, which the
 *  imported worked examples are) hides behind a disclosure so it can be read on
 *  demand without pushing the next question off the screen. */
function FieldHint({ text }: { text: string }) {
  const isLong = text.length > INLINE_HINT_MAX || text.includes("\n");
  if (!isLong) return <>{text}</>;
  return (
    <details className="form-hint-details">
      <summary>See example</summary>
      <div className="form-hint-details__body">{text}</div>
    </details>
  );
}

function FieldInput({
  field,
  value,
  onChange,
  readOnly,
  inputRef,
}: {
  field: FormFieldDef;
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
  inputRef?: (el: HTMLElement | null) => void;
}) {
  if (field.type === "yes_no") {
    const options = field.options ?? ["Yes", "No"];
    return (
      <div className="form-yesno-pills" role="group" aria-label={field.label}>
        {options.map((opt, i) => (
          <button
            key={opt}
            ref={i === 0 ? inputRef : undefined}
            type="button"
            className={`form-yesno-pill${value === opt ? " form-yesno-pill--active" : ""}`}
            disabled={readOnly}
            onClick={() => onChange(opt)}
          >
            {opt}
          </button>
        ))}
      </div>
    );
  }
  const common = { disabled: readOnly, required: field.required };
  if (field.type === "select") {
    const options = field.options ?? [];
    return (
      <Select ref={inputRef} value={value} onChange={(e) => onChange(e.target.value)} {...common}>
        <option value="">Select…</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </Select>
    );
  }
  if (field.type === "textarea") {
    return (
      <Textarea
        ref={inputRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder ?? undefined}
        rows={4}
        {...common}
      />
    );
  }
  return (
    <Input
      ref={inputRef}
      type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={field.placeholder ?? undefined}
      {...common}
    />
  );
}

export function computeFormProgress(schema: FormTemplateSchema, answers: FormAnswers) {
  const fields = collectFields(schema).filter((f) => f.required);
  const total = fields.length;
  const done = fields.filter((f) => isAnswered(answers[f.id])).length;
  const pct = total === 0 ? 100 : Math.round((done / total) * 100);
  return { done, total, pct };
}

export function DynamicFormRenderer({
  schema,
  answers,
  onChange,
  onSubmit,
  readOnly,
  submitting,
  branded,
  invalidFieldIds,
}: Props) {
  const sections = schema.sections ?? [];
  const groups = schema.repeatable_groups ?? [];
  const [step, setStep] = useState(0);
  const [panelKey, setPanelKey] = useState(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const fieldRefs = useRef<Record<string, HTMLElement | null>>({});
  const pendingFocus = useRef<string | null>(null);
  const [repeatable, setRepeatable] = useState<Record<string, Record<string, string>[]>>(() => {
    const init: Record<string, Record<string, string>[]> = {};
    for (const group of schema.repeatable_groups ?? []) {
      const existing = answers[group.id];
      init[group.id] = Array.isArray(existing) ? (existing as Record<string, string>[]) : [{}];
    }
    return init;
  });

  // Steps are: each section, then the repeatable groups (if any), then review.
  // Review replaces the old "Show all" checkbox — one way to see everything at
  // once, positioned where it is actually used: right before submitting.
  const groupStep = groups.length ? sections.length : -1;
  const reviewStep = sections.length + (groups.length ? 1 : 0);
  const onGroupStep = groupStep >= 0 && step === groupStep;
  const onReviewStep = step >= reviewStep;
  const currentSection = step < sections.length ? sections[step] : null;
  const currentSecProgress = currentSection ? sectionProgress(currentSection, answers) : null;
  const currentComplete = currentSection ? sectionComplete(currentSection, answers) : false;

  const missing = useMemo(() => findMissingRequired(schema, answers), [schema, answers]);
  const invalid = useMemo(() => new Set(invalidFieldIds ?? []), [invalidFieldIds]);

  const goToStep = useCallback((next: number) => {
    setStep(next);
    setPanelKey((k) => k + 1);
  }, []);

  /** Jump to the section holding a field and focus it once rendered. */
  const goToField = useCallback(
    (fieldId: string, sectionIdx: number) => {
      pendingFocus.current = fieldId;
      goToStep(sectionIdx);
    },
    [goToStep],
  );

  useEffect(() => {
    const target = pendingFocus.current;
    if (target) {
      const el = fieldRefs.current[target];
      pendingFocus.current = null;
      if (el) {
        el.focus();
        el.scrollIntoView({ block: "center", behavior: "smooth" });
        return;
      }
    }
    headingRef.current?.focus();
  }, [step, panelKey]);

  const setField = useCallback(
    (fieldId: string, value: string) => {
      onChange({ ...answers, [fieldId]: value });
    },
    [answers, onChange],
  );

  const renderSectionFields = (section: FormSectionDef) => (
    <div className="form-wizard__section-body">
      {section.fields.map((field) => {
        const answered = isAnswered(answers[field.id]);
        const wide = field.type === "textarea";
        const flagged = invalid.has(field.id);
        return (
          <div
            key={field.id}
            className={[
              "form-wizard__field",
              answered ? "form-wizard__field--answered" : "",
              wide ? "form-wizard__field--wide" : "",
              flagged ? "form-wizard__field--invalid" : "",
            ].filter(Boolean).join(" ")}
          >
            <FormField
              label={field.label}
              hint={field.help_text ? <FieldHint text={field.help_text} /> : undefined}
              required={field.required}
            >
              <FieldInput
                field={field}
                value={(answers[field.id] as string) ?? ""}
                onChange={(v) => setField(field.id, v)}
                readOnly={readOnly}
                inputRef={(el) => { fieldRefs.current[field.id] = el; }}
              />
            </FormField>
            {flagged && (
              <span className="form-wizard__field-error" role="alert">This answer is required</span>
            )}
            {answered && !readOnly && (
              <span className="form-wizard__field-check" aria-hidden="true">✓</span>
            )}
          </div>
        );
      })}
    </div>
  );

  const renderGroups = () =>
    groups.map((group) => (
      <section key={group.id} className="card form-wizard__panel">
        <h2 className="card__title">{group.title}</h2>
        {group.description && <p className="form-wizard__section-desc">{group.description}</p>}
        {(repeatable[group.id] ?? []).map((row, rowIdx) => (
          <div key={rowIdx} className="form-wizard__repeat-row">
            {group.fields.map((field) => (
              <FormField
                key={field.id}
                label={field.label}
                hint={field.help_text ? <FieldHint text={field.help_text} /> : undefined}
                required={field.required}
              >
                <FieldInput
                  field={field}
                  value={row[field.id] ?? ""}
                  readOnly={readOnly}
                  onChange={(v) => {
                    const rows = [...(repeatable[group.id] ?? [])];
                    rows[rowIdx] = { ...rows[rowIdx], [field.id]: v };
                    setRepeatable({ ...repeatable, [group.id]: rows });
                    onChange({ ...answers, [group.id]: rows });
                  }}
                />
              </FormField>
            ))}
          </div>
        ))}
        {!readOnly && (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => {
              const rows = [...(repeatable[group.id] ?? []), {}];
              setRepeatable({ ...repeatable, [group.id]: rows });
              onChange({ ...answers, [group.id]: rows });
            }}
          >
            Add row
          </Button>
        )}
      </section>
    ));

  /** Final read-through: every answer by section, gaps flagged and clickable. */
  const renderReview = () => (
    <section className="card form-wizard__panel form-wizard__panel--enter">
      <div className="form-wizard__panel-head">
        <h2 ref={headingRef} className="card__title" tabIndex={-1}>Review your answers</h2>
        {missing.length === 0 ? (
          <span className="form-wizard__section-done">Nothing missing</span>
        ) : (
          <span className="form-wizard__review-missing">
            {missing.length} required answer{missing.length === 1 ? "" : "s"} missing
          </span>
        )}
      </div>
      {sections.map((section, sectionIdx) => (
        <div key={section.id} className="form-wizard__review-section">
          <h3 className="form-wizard__review-title">
            {section.title}
            <button type="button" onClick={() => goToStep(sectionIdx)}>Edit</button>
          </h3>
          <dl className="form-wizard__review-list">
            {section.fields.map((field) => {
              const value = answers[field.id];
              const answered = isAnswered(value);
              return (
                <div
                  key={field.id}
                  className={`form-wizard__review-item${!answered && field.required ? " form-wizard__review-item--missing" : ""}`}
                >
                  <dt>{field.label}</dt>
                  <dd>
                    {answered ? (
                      String(value)
                    ) : field.required ? (
                      <button type="button" onClick={() => goToField(field.id, sectionIdx)}>
                        Missing — answer this
                      </button>
                    ) : (
                      <span className="form-wizard__review-blank">Not answered</span>
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
      ))}
    </section>
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit?.();
  };

  return (
    <div className={`form-wizard${branded ? " form-wizard--branded" : ""}`}>
      {schema.description && (
        <aside className="form-wizard__intro">
          <h2>How to fill this form</h2>
          <p>{schema.description}</p>
        </aside>
      )}

      {!readOnly && sections.length > 1 && (
        <div className="form-wizard__rail">
          <span className="form-wizard__rail-label" aria-live="polite">
            {onReviewStep
              ? "Review"
              : `Section ${Math.min(step + 1, sections.length)} of ${sections.length}`}
            {currentSecProgress ? ` · ${currentSecProgress.done}/${currentSecProgress.total}` : ""}
          </span>
          <div className="form-wizard__stepper" role="list">
            {sections.map((section, idx) => {
              const complete = sectionComplete(section, answers);
              const active = step === idx;
              return (
                <button
                  key={section.id}
                  type="button"
                  role="listitem"
                  title={section.title}
                  aria-label={`Section ${idx + 1}: ${section.title}`}
                  aria-current={active ? "step" : undefined}
                  className={`form-wizard__step${active ? " form-wizard__step--active" : ""}${complete ? " form-wizard__step--done" : ""}`}
                  onClick={() => goToStep(idx)}
                >
                  {complete ? "✓" : idx + 1}
                </button>
              );
            })}
          </div>
          {missing.length > 0 && (
            <button
              type="button"
              className="form-wizard__missing-jump"
              onClick={() => goToField(missing[0].field.id, missing[0].sectionIdx)}
            >
              {missing.length} required remaining →
            </button>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="form-wizard__form">
        {readOnly ? (
          <>
            {sections.map((section) => (
              <section key={section.id} className="card form-wizard__panel">
                <h2 className="card__title">{section.title}</h2>
                {section.description && (
                  <p className="form-wizard__section-desc">{section.description}</p>
                )}
                {renderSectionFields(section)}
              </section>
            ))}
            {renderGroups()}
          </>
        ) : onReviewStep ? (
          renderReview()
        ) : onGroupStep ? (
          renderGroups()
        ) : currentSection ? (
          <section key={`${currentSection.id}-${panelKey}`} className="card form-wizard__panel form-wizard__panel--enter">
            <div className="form-wizard__panel-head">
              <h2 ref={headingRef} className="card__title" tabIndex={-1}>
                {currentSection.title}
              </h2>
              {currentComplete && <span className="form-wizard__section-done">Complete</span>}
            </div>
            {currentSection.description && (
              <p className="form-wizard__section-desc">{currentSection.description}</p>
            )}
            {renderSectionFields(currentSection)}
          </section>
        ) : null}

        {!readOnly && (
          <div className="form-wizard__nav">
            <div className="form-wizard__nav-buttons">
              {step > 0 && (
                <Button type="button" variant="secondary" onClick={() => goToStep(step - 1)}>
                  Previous
                </Button>
              )}
              {step < reviewStep && (
                <Button type="button" className="form-wizard__next" onClick={() => goToStep(step + 1)}>
                  {step === reviewStep - 1 ? "Review" : "Next"}
                </Button>
              )}
              {onReviewStep && onSubmit && (
                <Button type="submit" className="form-wizard__submit" disabled={submitting}>
                  {submitting ? "Submitting…" : "Submit"}
                </Button>
              )}
            </div>
          </div>
        )}
      </form>
    </div>
  );
}
