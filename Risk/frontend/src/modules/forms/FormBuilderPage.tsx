import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, FormFieldDef, FormTemplate, FormTemplateSchema } from "../../api/client";
import { useToast } from "../../app/ToastContext";
import { PageHeader, Card, Button, FormField, Input, Select, Textarea, ConfirmDialog } from "../../components/ui";
import {
  addField,
  duplicateField,
  removeField,
  reorderField,
  reorderSection,
  updateField,
  updateSection,
} from "./schemaOps";

/** What is currently being dragged. `sectionIdx` is null for a whole section. */
type Drag = { index: number; sectionIdx: number | null };

// `tone` colours the chip beside each Type select, so the shape of a template
// reads at a glance instead of question-by-question. Deliberately no "danger"
// tone — red means invalid everywhere else in the app.
const FIELD_TYPES = [
  { value: "text", label: "Text", tone: "blue" },
  { value: "textarea", label: "Long text", tone: "violet" },
  { value: "yes_no", label: "Yes / No", tone: "green" },
  { value: "select", label: "Select list", tone: "teal" },
  { value: "number", label: "Number", tone: "amber" },
  { value: "date", label: "Date", tone: "sky" },
];

function typeMeta(type: string) {
  return FIELD_TYPES.find((t) => t.value === type) ?? { label: type, tone: "blue" };
}

function newFieldId() {
  return `field_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

function newField(): FormFieldDef {
  return {
    id: newFieldId(),
    label: "New question",
    type: "text",
    // Matches FormFieldSchema's server-side default, which is True.
    required: true,
  };
}

export function FormBuilderPage() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [schema, setSchema] = useState<FormTemplateSchema>({ sections: [], repeatable_groups: [] });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [dropTarget, setDropTarget] = useState<Drag | null>(null);
  // Index of the section awaiting removal confirmation. null = dialog closed.
  const [pendingSection, setPendingSection] = useState<number | null>(null);
  // A card only becomes draggable while its grip is held. Marking it draggable
  // permanently would stop text selection inside its own inputs.
  const [armed, setArmed] = useState<string | null>(null);

  useEffect(() => {
    if (!templateId) return;
    api.get<FormTemplate>(`/forms/templates/${templateId}`).then((t) => {
      setName(t.name);
      setSchema(t.schema);
    });
  }, [templateId]);

  const questionCount = useMemo(
    () => schema.sections.reduce((n, s) => n + s.fields.length, 0),
    [schema],
  );

  // Sections start folded: a 7-section, 38-question template opens as a
  // readable outline rather than a screen-and-a-half of identical cards.
  const isOpen = (sectionId: string) => expanded[sectionId] ?? false;
  const toggle = (sectionId: string) =>
    setExpanded((e) => ({ ...e, [sectionId]: !isOpen(sectionId) }));
  const setAll = (open: boolean) =>
    setExpanded(Object.fromEntries(schema.sections.map((s) => [s.id, open])));

  const jumpTo = (sectionId: string) => {
    setExpanded((e) => ({ ...e, [sectionId]: true }));
    // Wait for the section to render open before scrolling to it.
    requestAnimationFrame(() =>
      document.getElementById(`section-${sectionId}`)?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  const sameList = (a: Drag | null, b: Drag) => a != null && a.sectionIdx === b.sectionIdx;

  const onDragStart = (item: Drag) => (e: React.DragEvent) => {
    setDrag(item);
    e.dataTransfer.effectAllowed = "move";
    // Firefox ignores a drag that carries no data.
    e.dataTransfer.setData("text/plain", String(item.index));
  };

  /** Highlight a valid target. Questions stay within their own section. */
  const onDragOver = (item: Drag) => (e: React.DragEvent) => {
    if (!sameList(drag, item)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dropTarget?.index !== item.index || dropTarget?.sectionIdx !== item.sectionIdx) {
      setDropTarget(item);
    }
  };

  const onDrop = (item: Drag) => (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (sameList(drag, item) && drag!.index !== item.index) {
      setSchema(
        item.sectionIdx === null
          ? reorderSection(schema, drag!.index, item.index)
          : reorderField(schema, item.sectionIdx, drag!.index, item.index),
      );
    }
    endDrag();
  };

  const endDrag = () => {
    setDrag(null);
    setDropTarget(null);
    setArmed(null);
  };

  /** Keyboard equivalent, since native drag-and-drop is mouse-only. */
  const onGripKeyDown = (item: Drag, listLength: number) => (e: React.KeyboardEvent) => {
    const delta = e.key === "ArrowUp" ? -1 : e.key === "ArrowDown" ? 1 : 0;
    if (!delta) return;
    const to = item.index + delta;
    if (to < 0 || to >= listLength) return;
    e.preventDefault();
    setSchema(
      item.sectionIdx === null
        ? reorderSection(schema, item.index, to)
        : reorderField(schema, item.sectionIdx, item.index, to),
    );
  };

  const grip = (item: Drag, key: string, listLength: number, label: string) => (
    <button
      type="button"
      className="drag-grip"
      title={`${label} — drag to reorder, or focus and use ↑ ↓`}
      aria-label={`Reorder ${label}. Press arrow up or arrow down to move it.`}
      onMouseDown={() => setArmed(key)}
      onMouseUp={() => setArmed(null)}
      onKeyDown={onGripKeyDown(item, listLength)}
    >
      ⠿
    </button>
  );

  const dropClass = (item: Drag) =>
    dropTarget?.index === item.index && dropTarget?.sectionIdx === item.sectionIdx
      ? " is-drop-target"
      : "";

  const addSection = () => {
    const id = `section_${Date.now()}`;
    setSchema({
      ...schema,
      sections: [...schema.sections, { id, title: "New section", fields: [] }],
    });
    setExpanded((e) => ({ ...e, [id]: true }));
  };

  const confirmRemoveSection = () => {
    if (pendingSection === null) return;
    setSchema({ ...schema, sections: schema.sections.filter((_, i) => i !== pendingSection) });
    setPendingSection(null);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!templateId) return;
    setSaving(true);
    try {
      await api.patch(`/forms/templates/${templateId}`, { name, schema });
      toast.success("Template saved");
      navigate("/admin/forms");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        breadcrumb="Forms"
        title="Edit form template"
        subtitle={`${schema.sections.length} sections · ${questionCount} questions`}
        action={
          <div className="form-builder__header-actions">
            <Button type="button" size="sm" variant="secondary" onClick={() => setAll(true)}>
              Expand all
            </Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => setAll(false)}>
              Collapse all
            </Button>
          </div>
        }
      />

      <div className="form-builder">
        {schema.sections.length > 1 && (
          <aside className="form-builder__outline" aria-label="Sections">
            <h2>Sections</h2>
            <ol>
              {schema.sections.map((section, sIdx) => (
                <li key={section.id}>
                  <button type="button" onClick={() => jumpTo(section.id)}>
                    <span className="form-builder__outline-num">S{sIdx + 1}</span>
                    <span className="form-builder__outline-title">{section.title}</span>
                    <span className="form-builder__outline-count">{section.fields.length}</span>
                  </button>
                </li>
              ))}
            </ol>
          </aside>
        )}

        <form onSubmit={save} className="form-builder__main">
          <Card>
            <FormField label="Template name">
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </FormField>
            <FormField
              label="How to fill this form"
              hint="Shown above the form and carried into the downloadable workbook. Leave blank to omit."
            >
              <Textarea
                className="input input--textarea input--compact"
                value={schema.description ?? ""}
                rows={3}
                placeholder="e.g. Answer every starred question. Where a question asks for evidence, give the policy name and date."
                onChange={(e) => setSchema({ ...schema, description: e.target.value })}
              />
            </FormField>
          </Card>

          {schema.sections.map((section, sIdx) => {
            const open = isOpen(section.id);
            return (
              <Card
                key={section.id}
                className={
                  `mb-24 form-builder-section${dropClass({ index: sIdx, sectionIdx: null })}` +
                  (drag?.sectionIdx === null && drag.index === sIdx ? " is-dragging" : "")
                }
                id={`section-${section.id}`}
                draggable={armed === section.id}
                onDragStart={onDragStart({ index: sIdx, sectionIdx: null })}
                onDragOver={onDragOver({ index: sIdx, sectionIdx: null })}
                onDrop={onDrop({ index: sIdx, sectionIdx: null })}
                onDragEnd={endDrag}
              >
                {/* Display-only bar. Nothing editable lives here, so nothing in
                    the body has to be indented around the chevron. */}
                <div className="form-builder-section__header">
                  {grip(
                    { index: sIdx, sectionIdx: null },
                    section.id,
                    schema.sections.length,
                    `section ${sIdx + 1}`,
                  )}
                  <button
                    type="button"
                    className="form-builder-section__toggle"
                    onClick={() => toggle(section.id)}
                    aria-expanded={open}
                    aria-label={open ? `Collapse ${section.title}` : `Expand ${section.title}`}
                  >
                    {open ? "▾" : "▸"}
                  </button>
                  <span className="form-builder-section__num">S{sIdx + 1}</span>
                  <button
                    type="button"
                    className="form-builder-section__name"
                    onClick={() => toggle(section.id)}
                  >
                    {section.title || "Untitled section"}
                  </button>
                  <span className="form-builder-section__count">
                    {section.fields.length} {section.fields.length === 1 ? "question" : "questions"}
                  </span>
                  <div className="form-builder-section__actions">
                    <Button type="button" size="sm" variant="danger" onClick={() => setPendingSection(sIdx)}>
                      Remove
                    </Button>
                  </div>
                </div>

                {open && (
                  <div className="form-builder-section__body">
                    <FormField label="Section title">
                      <Input
                        value={section.title}
                        onChange={(e) => setSchema(updateSection(schema, sIdx, { title: e.target.value }))}
                      />
                    </FormField>
                    <FormField label="Section intro" hint="Optional line shown under the section title.">
                      <Textarea
                        className="input input--textarea input--compact"
                        value={section.description ?? ""}
                        rows={2}
                        onChange={(e) =>
                          setSchema(updateSection(schema, sIdx, { description: e.target.value }))
                        }
                      />
                    </FormField>

                    {section.fields.map((field, fIdx) => {
                      const meta = typeMeta(field.type);
                      return (
                        <div
                          key={field.id}
                          className={
                            `form-builder-field${dropClass({ index: fIdx, sectionIdx: sIdx })}` +
                            (drag?.sectionIdx === sIdx && drag.index === fIdx ? " is-dragging" : "")
                          }
                          draggable={armed === field.id}
                          onDragStart={onDragStart({ index: fIdx, sectionIdx: sIdx })}
                          onDragOver={onDragOver({ index: fIdx, sectionIdx: sIdx })}
                          onDrop={onDrop({ index: fIdx, sectionIdx: sIdx })}
                          onDragEnd={endDrag}
                        >
                          <div className="form-builder-field__head">
                            {grip(
                              { index: fIdx, sectionIdx: sIdx },
                              field.id,
                              section.fields.length,
                              `question ${fIdx + 1}`,
                            )}
                            <span className="form-builder-field__num">Q{fIdx + 1}</span>
                            <span className={`type-chip type-chip--${meta.tone}`}>{meta.label}</span>
                            {field.required && <span className="type-chip type-chip--required">Required</span>}
                            <div className="form-builder-field__tools">
                              <button
                                type="button"
                                className="icon-btn icon-btn--copy"
                                title="Duplicate question"
                                aria-label="Duplicate question"
                                onClick={() => setSchema(duplicateField(schema, sIdx, fIdx, newFieldId()))}
                              >
                                ⧉
                              </button>
                              <button
                                type="button"
                                className="icon-btn icon-btn--danger"
                                title="Remove question"
                                aria-label="Remove question"
                                onClick={() => setSchema(removeField(schema, sIdx, fIdx))}
                              >
                                ✕
                              </button>
                            </div>
                          </div>

                          <div className="form-builder-field__row">
                            <FormField label="Question">
                              <Input
                                value={field.label}
                                onChange={(e) =>
                                  setSchema(updateField(schema, sIdx, fIdx, { label: e.target.value }))
                                }
                              />
                            </FormField>
                            <FormField label="Type">
                              <Select
                                value={field.type}
                                onChange={(e) =>
                                  setSchema(updateField(schema, sIdx, fIdx, { type: e.target.value }))
                                }
                              >
                                {FIELD_TYPES.map((t) => (
                                  <option key={t.value} value={t.value}>{t.label}</option>
                                ))}
                              </Select>
                            </FormField>
                          </div>

                          {(field.type === "select" || field.type === "yes_no") && (
                            <FormField label="Options (comma-separated)" hint="e.g. Yes, No, N/A">
                              <Input
                                value={(field.options ?? []).join(", ")}
                                onChange={(e) =>
                                  setSchema(
                                    updateField(schema, sIdx, fIdx, {
                                      options: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                                    }),
                                  )
                                }
                              />
                            </FormField>
                          )}

                          <div className="form-builder-field__row">
                            <FormField
                              label="Help text"
                              hint="Guidance or a worked example. Long text collapses behind a 'See example' toggle."
                            >
                              <Textarea
                                className="input input--textarea input--compact"
                                value={field.help_text ?? ""}
                                rows={2}
                                onChange={(e) =>
                                  setSchema(updateField(schema, sIdx, fIdx, { help_text: e.target.value }))
                                }
                              />
                            </FormField>
                            <FormField label="Placeholder" hint="Ghost text inside the empty input.">
                              <Input
                                value={field.placeholder ?? ""}
                                onChange={(e) =>
                                  setSchema(updateField(schema, sIdx, fIdx, { placeholder: e.target.value }))
                                }
                              />
                            </FormField>
                          </div>

                          <label className="form-builder-field__required">
                            <input
                              type="checkbox"
                              checked={field.required ?? false}
                              onChange={(e) =>
                                setSchema(updateField(schema, sIdx, fIdx, { required: e.target.checked }))
                              }
                            />
                            Required
                          </label>
                        </div>
                      );
                    })}

                    <div>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => setSchema(addField(schema, sIdx, newField()))}
                      >
                        Add question
                      </Button>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}

          <div className="form-builder-footer">
            <Button type="button" variant="secondary" onClick={addSection}>Add section</Button>
            <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save template"}</Button>
          </div>
        </form>
      </div>
      <ConfirmDialog
        open={pendingSection !== null}
        title="Remove section?"
        message={
          <>
            <strong>{pendingSection !== null ? schema.sections[pendingSection]?.title : ""}</strong>
            {pendingSection !== null && schema.sections[pendingSection]?.fields.length
              ? ` and its ${schema.sections[pendingSection].fields.length} question(s) will be removed.`
              : " will be removed."}
            {" "}Nothing is saved until you press Save template.
          </>
        }
        confirmLabel="Remove section"
        onConfirm={confirmRemoveSection}
        onCancel={() => setPendingSection(null)}
      />
    </div>
  );
}
