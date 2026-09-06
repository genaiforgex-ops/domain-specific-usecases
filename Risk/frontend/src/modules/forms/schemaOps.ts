import type { FormFieldDef, FormSectionDef, FormTemplateSchema } from "../../api/client";

/**
 * Pure edits on a form template schema.
 *
 * Kept out of the component and free of mutation on purpose: the builder's
 * original handlers did `const sections = [...schema.sections]` and then wrote
 * through `sections[i].fields`, which is a shallow copy — the nested section and
 * field objects stayed shared with the previous state. Every helper here copies
 * each level it touches, and the tests assert the input is left alone.
 */

/**
 * Lift an entry out and drop it back in at `to`.
 *
 * Splice semantics rather than a swap, because a drag can land anywhere in the
 * list — swapping would only be correct for single-step moves. Out-of-range or
 * no-op targets return the original array so callers can compare by identity.
 */
function reorder<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length || from < 0 || from >= items.length || from === to) {
    return items;
  }
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

export function reorderSection(schema: FormTemplateSchema, from: number, to: number): FormTemplateSchema {
  const sections = reorder(schema.sections, from, to);
  return sections === schema.sections ? schema : { ...schema, sections };
}

export function reorderField(
  schema: FormTemplateSchema,
  sectionIdx: number,
  from: number,
  to: number,
): FormTemplateSchema {
  const section = schema.sections[sectionIdx];
  if (!section) return schema;
  const fields = reorder(section.fields, from, to);
  if (fields === section.fields) return schema;
  const sections = [...schema.sections];
  sections[sectionIdx] = { ...section, fields };
  return { ...schema, sections };
}

/**
 * Insert a copy of a question directly below it.
 *
 * The clone must get a fresh `id`: answers are keyed by field id, so a
 * duplicated id would make the two questions share a single answer.
 */
export function duplicateField(
  schema: FormTemplateSchema,
  sectionIdx: number,
  fieldIdx: number,
  newId: string,
): FormTemplateSchema {
  const section = schema.sections[sectionIdx];
  const source = section?.fields[fieldIdx];
  if (!source) return schema;

  const clone: FormFieldDef = {
    ...source,
    id: newId,
    // options is an array — a spread of `source` would hand the copy the same
    // one, so editing either question's option list would edit both.
    options: source.options ? [...source.options] : source.options,
  };
  const fields = [...section.fields];
  fields.splice(fieldIdx + 1, 0, clone);
  const sections = [...schema.sections];
  sections[sectionIdx] = { ...section, fields };
  return { ...schema, sections };
}

/** Replace part of one field, copying every level on the way down. */
export function updateField(
  schema: FormTemplateSchema,
  sectionIdx: number,
  fieldIdx: number,
  patch: Partial<FormFieldDef>,
): FormTemplateSchema {
  const section = schema.sections[sectionIdx];
  if (!section?.fields[fieldIdx]) return schema;
  const fields = [...section.fields];
  fields[fieldIdx] = { ...fields[fieldIdx], ...patch };
  const sections = [...schema.sections];
  sections[sectionIdx] = { ...section, fields };
  return { ...schema, sections };
}

/** Replace part of one section, copying every level on the way down. */
export function updateSection(
  schema: FormTemplateSchema,
  sectionIdx: number,
  patch: Partial<FormSectionDef>,
): FormTemplateSchema {
  const section = schema.sections[sectionIdx];
  if (!section) return schema;
  const sections = [...schema.sections];
  sections[sectionIdx] = { ...section, ...patch };
  return { ...schema, sections };
}

export function addField(
  schema: FormTemplateSchema,
  sectionIdx: number,
  field: FormFieldDef,
): FormTemplateSchema {
  const section = schema.sections[sectionIdx];
  if (!section) return schema;
  const sections = [...schema.sections];
  sections[sectionIdx] = { ...section, fields: [...section.fields, field] };
  return { ...schema, sections };
}

export function removeField(
  schema: FormTemplateSchema,
  sectionIdx: number,
  fieldIdx: number,
): FormTemplateSchema {
  const section = schema.sections[sectionIdx];
  if (!section) return schema;
  const sections = [...schema.sections];
  sections[sectionIdx] = {
    ...section,
    fields: section.fields.filter((_, i) => i !== fieldIdx),
  };
  return { ...schema, sections };
}
