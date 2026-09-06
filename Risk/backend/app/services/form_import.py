import io
import re
from typing import Any

from openpyxl import load_workbook


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return s or "field"


# Values the Response column uses to declare an answer *type* rather than to
# give guidance. They drive field-type inference and must not leak into
# help_text, where "Freetext" under a question reads as noise.
_TYPE_HINT_TOKENS = {
    "yes", "no", "yes/no", "freetext", "free text", "text",
    "na", "n/a", "number", "numeric", "date",
}


def _is_type_hint(value: str) -> bool:
    return (value or "").strip().lower() in _TYPE_HINT_TOKENS


def _infer_field_type(label: str, response_hint: str | None, remarks_hint: str | None) -> str:
    hint = (response_hint or "").strip().lower()
    if hint in ("yes", "no", "yes/no"):
        return "yes_no"
    if hint in ("freetext", "free text"):
        return "textarea"
    if len((response_hint or "")) > 120 or len((remarks_hint or "")) > 80:
        return "textarea"
    return "text"


# Header text -> the logical column it names. Matched by prefix on a normalised
# (lowercased, punctuation-stripped) header cell, so "Type " and "Additional
# Remarks, If any" both resolve.
_HEADER_ALIASES: list[tuple[str, str]] = [
    ("slno", "sl_no"),
    ("parameter", "parameter"),
    ("type", "param_type"),
    ("response", "response"),
    ("additionalremarks", "remarks"),
    ("remarks", "remarks"),
]

# Used when a sheet has no recognisable header row.
_LEGACY_COLUMNS = {"sl_no": 0, "parameter": 1, "param_type": 2, "response": 3, "remarks": 4}


def _normalise_header(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _detect_columns(sheet, scan_rows: int = 10) -> dict[str, int]:
    """Locate the Sl.No/Parameter/Type/Response/Remarks columns by header text.

    The columns are NOT contiguous in a real VDD workbook: cells are merged into
    groups, so Parameter spans B:D and Response spans F:I, putting Type at E and
    Remarks at J. Reading five cells from A therefore picks up three empty
    columns and mistakes Type for Remarks — which is why guidance, Yes/No types
    and long-text detection were all silently lost. Anchor on the header row
    instead, and fall back to the old positional layout if there isn't one.
    """
    for row in sheet.iter_rows(min_row=1, max_row=scan_rows, values_only=True):
        cells = [_normalise_header(str(c)) if c is not None else "" for c in row]
        if "slno" not in cells or "parameter" not in cells:
            continue
        columns: dict[str, int] = {}
        for idx, cell in enumerate(cells):
            if not cell:
                continue
            for prefix, key in _HEADER_ALIASES:
                if cell.startswith(prefix) and key not in columns:
                    columns[key] = idx
                    break
        return columns
    return dict(_LEGACY_COLUMNS)


def list_workbook_sheets(data: bytes) -> list[dict[str, Any]]:
    """Return sheet metadata for an uploaded workbook."""
    wb = load_workbook(filename=io.BytesIO(data), read_only=True, data_only=True)
    sheets: list[dict[str, Any]] = []
    for idx, sheet in enumerate(wb.worksheets):
        row_count = 0
        for row in sheet.iter_rows(min_row=1, values_only=True):
            if any(c is not None and str(c).strip() for c in row):
                row_count += 1
        sheets.append({"index": idx, "name": sheet.title, "row_count": row_count})
    wb.close()
    return sheets


def parse_vdd_sheet(
    data: bytes,
    *,
    sheet_index: int = 1,
    template_name: str = "Vendor Due Diligence Assessment",
) -> dict[str, Any]:
    """Parse a VDD workbook sheet into a form template schema."""
    wb = load_workbook(filename=io.BytesIO(data), read_only=True, data_only=True)
    if sheet_index < 0 or sheet_index >= len(wb.worksheets):
        wb.close()
        raise ValueError(f"Sheet index {sheet_index} out of range (0–{len(wb.worksheets) - 1})")
    sheet = wb.worksheets[sheet_index]
    columns = _detect_columns(sheet)

    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    field_counter = 0
    # Sections come from the Sl. No. column's title rows. Only when a sheet has
    # none do we fall back to grouping by the Type column — otherwise Type would
    # shatter the document's real sections into broad categories.
    saw_titled_section = False

    for row in sheet.iter_rows(min_row=1, values_only=True):
        cells = [str(c).strip() if c is not None else "" for c in row]

        def _col(key: str) -> str:
            idx = columns.get(key)
            return cells[idx] if idx is not None and idx < len(cells) else ""

        sl_no = _col("sl_no")
        parameter = _col("parameter")
        param_type = _col("param_type")
        response = _col("response")
        remarks = _col("remarks")
        if not parameter and not sl_no:
            continue
        if parameter.lower() in ("due diligence template", "sl. no.", "sl no.", "parameter"):
            continue
        if sl_no.lower() in ("sl. no.", "sl no.") and parameter.lower() == "parameter":
            continue

        def _is_numberish(val: str) -> bool:
            try:
                float(val)
                return True
            except ValueError:
                return False

        # Section header: title in first column when it is not a serial number
        if sl_no and not _is_numberish(sl_no) and not parameter:
            section_id = _slug(sl_no)
            current_section = {"id": section_id, "title": sl_no, "fields": []}
            sections.append(current_section)
            saw_titled_section = True
            continue
        if not sl_no and parameter and not param_type and not _is_numberish(parameter):
            section_id = _slug(parameter)
            current_section = {"id": section_id, "title": parameter, "fields": []}
            sections.append(current_section)
            saw_titled_section = True
            continue

        if not parameter:
            continue

        # Group by Type column when it changes — only for sheets that gave us no
        # section titles of their own, since Type is a broad category ("General
        # information") that would otherwise flatten the real section structure.
        if param_type and not saw_titled_section:
            section_id = _slug(param_type)
            if not current_section or current_section["id"] != section_id:
                current_section = {"id": section_id, "title": param_type, "fields": []}
                if not any(s["id"] == section_id for s in sections):
                    sections.append(current_section)
                else:
                    current_section = next(s for s in sections if s["id"] == section_id)
        elif current_section is None:
            current_section = {"id": "general", "title": "General", "fields": []}
            sections.append(current_section)

        field_counter += 1
        field_id = f"q{field_counter}_{_slug(parameter)[:40]}"
        ftype = _infer_field_type(parameter, response, remarks)
        field: dict[str, Any] = {
            "id": field_id,
            "label": parameter,
            "type": ftype,
            "required": True,
        }
        # The Response column carries the sheet's guidance — worked examples and
        # instructions like "Please provide in Details". It becomes help_text,
        # never a placeholder: several entries run to multiple lines and would be
        # unreadable as ghost text. Entries that merely declare the answer type
        # ("Yes", "Freetext") have already been consumed by _infer_field_type and
        # are dropped here rather than shown to the user as advice.
        if response and not _is_type_hint(response):
            field["help_text"] = response
        if ftype == "yes_no":
            field["options"] = ["Yes", "No"]

        current_section["fields"].append(field)

        if remarks and remarks.lower().startswith("please"):
            field_counter += 1
            current_section["fields"].append(
                {
                    "id": f"q{field_counter}_{_slug(parameter)[:30]}_remarks",
                    "label": f"{parameter} — Additional remarks",
                    "type": "textarea",
                    "required": False,
                    "help_text": remarks,
                }
            )

    wb.close()
    sections = [s for s in sections if s.get("fields")]
    return {
        "name": template_name,
        "schema": {"sections": sections, "repeatable_groups": []},
    }


def parse_vdd_sheet2(data: bytes, *, template_name: str = "Vendor Due Diligence Assessment") -> dict[str, Any]:
    """Backward-compatible alias: parse Sheet 2 (index 1) of the VDD workbook."""
    return parse_vdd_sheet(data, sheet_index=1, template_name=template_name)
