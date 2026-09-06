import { describe, expect, it } from "vitest";
import type { FormTemplateSchema } from "../../api/client";
import {
  addField,
  duplicateField,
  reorderField,
  reorderSection,
  removeField,
  updateField,
  updateSection,
} from "./schemaOps";

function schema(): FormTemplateSchema {
  return {
    description: "How to fill this",
    sections: [
      {
        id: "s1",
        title: "Identity",
        fields: [
          { id: "q1", label: "Name", type: "text", required: true },
          { id: "q2", label: "Encrypted?", type: "yes_no", required: true, options: ["Yes", "No"] },
        ],
      },
      {
        id: "s2",
        title: "Commercial",
        fields: [{ id: "q3", label: "Headcount", type: "number", required: false }],
      },
    ],
    repeatable_groups: [],
  };
}

/** Deep snapshot, so a mutation anywhere in the tree is detectable. */
const snapshot = (s: FormTemplateSchema) => JSON.stringify(s);

describe("reorderSection", () => {
  it("moves a section to a new index", () => {
    const result = reorderSection(schema(), 0, 1);
    expect(result.sections.map((s) => s.id)).toEqual(["s2", "s1"]);
  });

  it("is a no-op outside the list or onto itself", () => {
    const start = schema();
    expect(reorderSection(start, 0, -1)).toBe(start);
    expect(reorderSection(start, 1, 2)).toBe(start);
    expect(reorderSection(start, 0, 0)).toBe(start);
  });
});

describe("reorderField", () => {
  it("moves a question within its section", () => {
    const result = reorderField(schema(), 0, 0, 1);
    expect(result.sections[0].fields.map((f) => f.id)).toEqual(["q2", "q1"]);
  });

  it("drops a dragged item at an arbitrary index, not just adjacent", () => {
    // Splice semantics: dragging the first item to the end must land it last,
    // which a swap would get wrong for any distance greater than one.
    const start = addField(schema(), 0, { id: "q9", label: "Third", type: "text" });
    const result = reorderField(start, 0, 0, 2);
    expect(result.sections[0].fields.map((f) => f.id)).toEqual(["q2", "q9", "q1"]);
  });

  it("leaves other sections alone", () => {
    const start = schema();
    const result = reorderField(start, 0, 0, 1);
    expect(result.sections[1]).toBe(start.sections[1]);
  });

  it("is a no-op outside the list, or on a section that isn't there", () => {
    const start = schema();
    expect(reorderField(start, 0, 0, -1)).toBe(start);
    expect(reorderField(start, 0, 1, 2)).toBe(start);
    expect(reorderField(start, 9, 0, 1)).toBe(start);
  });
});

describe("duplicateField", () => {
  it("inserts the copy directly below the source", () => {
    const result = duplicateField(schema(), 0, 0, "q1_copy");
    expect(result.sections[0].fields.map((f) => f.id)).toEqual(["q1", "q1_copy", "q2"]);
  });

  it("copies every property except the id", () => {
    const result = duplicateField(schema(), 0, 1, "q2_copy");
    const [source, clone] = [result.sections[0].fields[1], result.sections[0].fields[2]];

    expect(clone.id).toBe("q2_copy");
    expect(clone.id).not.toBe(source.id);
    expect({ ...clone, id: undefined }).toEqual({ ...source, id: undefined });
  });

  it("gives the clone its own options array", () => {
    // Sharing it would make editing one question's options edit both.
    const result = duplicateField(schema(), 0, 1, "q2_copy");
    const [source, clone] = [result.sections[0].fields[1], result.sections[0].fields[2]];

    expect(clone.options).toEqual(source.options);
    expect(clone.options).not.toBe(source.options);
  });

  it("is a no-op for a field that isn't there", () => {
    const start = schema();
    expect(duplicateField(start, 0, 9, "x")).toBe(start);
  });
});

describe("updateField / updateSection / addField / removeField", () => {
  it("patches a single field", () => {
    const result = updateField(schema(), 0, 0, { label: "Legal name", help_text: "As registered" });
    expect(result.sections[0].fields[0]).toMatchObject({
      id: "q1",
      label: "Legal name",
      help_text: "As registered",
      type: "text",
    });
  });

  it("patches a section without touching its fields", () => {
    const start = schema();
    const result = updateSection(start, 0, { description: "Who the provider is" });
    expect(result.sections[0].description).toBe("Who the provider is");
    expect(result.sections[0].fields).toBe(start.sections[0].fields);
  });

  it("appends and removes fields", () => {
    const added = addField(schema(), 1, { id: "q4", label: "Tier", type: "select" });
    expect(added.sections[1].fields.map((f) => f.id)).toEqual(["q3", "q4"]);
    expect(removeField(added, 1, 0).sections[1].fields.map((f) => f.id)).toEqual(["q4"]);
  });
});

describe("immutability", () => {
  // The bug these helpers replace: [...schema.sections] is a shallow copy, so
  // writing through sections[i].fields edited the previous state in place.
  const cases: Array<[string, (s: FormTemplateSchema) => FormTemplateSchema]> = [
    ["reorderSection", (s) => reorderSection(s, 0, 1)],
    ["reorderField", (s) => reorderField(s, 0, 0, 1)],
    ["duplicateField", (s) => duplicateField(s, 0, 0, "copy")],
    ["updateField", (s) => updateField(s, 0, 0, { label: "changed" })],
    ["updateSection", (s) => updateSection(s, 0, { title: "changed" })],
    ["addField", (s) => addField(s, 0, { id: "new", label: "New", type: "text" })],
    ["removeField", (s) => removeField(s, 0, 0)],
  ];

  it.each(cases)("%s does not mutate the schema it is given", (_name, op) => {
    const start = schema();
    const before = snapshot(start);
    op(start);
    expect(snapshot(start)).toBe(before);
  });
});
