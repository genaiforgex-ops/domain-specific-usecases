"""Produce native OOXML tracked-change markup (w:ins / w:del) for AI edits.

When the AI applies structured operations to a DOCX, wrapping the mutations in
revision markup makes them appear as author-attributed redlines in Word /
OnlyOffice — exactly like human edits — instead of silently overwriting text.
The author is set to a distinct AI identity so reviewers and vendors can tell
machine-proposed changes apart from lawyer edits.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# xml:space lives in the built-in XML namespace; qn() does not map the "xml"
# prefix, so reference it directly.
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


@dataclass
class TrackChangeContext:
    """Author/date stamp plus a monotonic revision-id counter for one document."""

    author: str
    date: str
    _next_id: int = 1

    def new_id(self) -> str:
        val = self._next_id
        self._next_id += 1
        return str(val)


def make_context(doc, author: str, date: str) -> TrackChangeContext:
    """Seed the revision-id counter above any existing w:ins/w:del id so AI
    revisions never collide with human (OnlyOffice) revisions in the same doc."""
    max_id = 0
    for el in doc.element.iter():
        if el.tag in (qn("w:ins"), qn("w:del")):
            try:
                max_id = max(max_id, int(el.get(qn("w:id")) or 0))
            except (TypeError, ValueError):
                pass
    return TrackChangeContext(author=author, date=date, _next_id=max_id + 1)


def _stamp(el, ctx: TrackChangeContext) -> None:
    el.set(qn("w:id"), ctx.new_id())
    el.set(qn("w:author"), ctx.author)
    el.set(qn("w:date"), ctx.date)


def _text_run(text: str, rpr_template) -> "OxmlElement":
    r = OxmlElement("w:r")
    if rpr_template is not None:
        r.append(copy.deepcopy(rpr_template))
    t = OxmlElement("w:t")
    t.set(_XML_SPACE, "preserve")
    t.text = text
    r.append(t)
    return r


def _del_run(text: str, rpr_template, ctx: TrackChangeContext) -> "OxmlElement":
    """A <w:del> wrapping one run whose text is stored as <w:delText>."""
    r = OxmlElement("w:r")
    if rpr_template is not None:
        r.append(copy.deepcopy(rpr_template))
    dt = OxmlElement("w:delText")
    dt.set(_XML_SPACE, "preserve")
    dt.text = text
    r.append(dt)
    del_el = OxmlElement("w:del")
    _stamp(del_el, ctx)
    del_el.append(r)
    return del_el


def _ins_run(text: str, rpr_template, ctx: TrackChangeContext) -> "OxmlElement":
    ins = OxmlElement("w:ins")
    _stamp(ins, ctx)
    ins.append(_text_run(text, rpr_template))
    return ins


def _first_rpr(para):
    if para.runs:
        return para.runs[0]._r.find(qn("w:rPr"))
    return None


def _wrap_run_deleted(run, ctx: TrackChangeContext) -> None:
    """Convert an existing run into a tracked deletion in place."""
    r = run._r
    parent = r.getparent()
    for t in r.findall(qn("w:t")):
        t.tag = qn("w:delText")
    del_el = OxmlElement("w:del")
    _stamp(del_el, ctx)
    parent.replace(r, del_el)
    del_el.append(r)


def delete_paragraph_tracked(para, ctx: TrackChangeContext) -> bool:
    """Mark every run in the paragraph as a tracked deletion."""
    for run in list(para.runs):
        _wrap_run_deleted(run, ctx)
    return True


def replace_paragraph_tracked(para, new_text: str, ctx: TrackChangeContext) -> bool:
    """Strike the whole paragraph and append the new text as a tracked insertion."""
    rpr = _first_rpr(para)
    rpr_copy = copy.deepcopy(rpr) if rpr is not None else None
    for run in list(para.runs):
        _wrap_run_deleted(run, ctx)
    if new_text:
        para._p.append(_ins_run(new_text, rpr_copy, ctx))
    return True


def replace_span_tracked(para, old: str, new: str, ctx: TrackChangeContext) -> bool:
    """Redline only the matched span: keep prefix/suffix, strike `old`, insert `new`."""
    full = para.text
    idx = full.find(old)
    if idx < 0:
        return False
    prefix, suffix = full[:idx], full[idx + len(old):]
    rpr = _first_rpr(para)
    rpr_copy = copy.deepcopy(rpr) if rpr is not None else None

    for run in list(para.runs):
        run._r.getparent().remove(run._r)

    p = para._p
    if prefix:
        p.append(_text_run(prefix, rpr_copy))
    if old:
        p.append(_del_run(old, rpr_copy, ctx))
    if new:
        p.append(_ins_run(new, rpr_copy, ctx))
    if suffix:
        p.append(_text_run(suffix, rpr_copy))
    return True


def mark_paragraph_inserted(para, ctx: TrackChangeContext) -> bool:
    """Mark a freshly inserted paragraph (its runs and its paragraph mark) as inserted."""
    for run in list(para.runs):
        r = run._r
        parent = r.getparent()
        ins = OxmlElement("w:ins")
        _stamp(ins, ctx)
        parent.replace(r, ins)
        ins.append(r)
    # Mark the paragraph mark itself inserted so accept/reject merges cleanly.
    pPr = para._p.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        para._p.insert(0, pPr)
    rPr = pPr.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        pPr.append(rPr)
    ins_mark = OxmlElement("w:ins")
    _stamp(ins_mark, ctx)
    rPr.insert(0, ins_mark)
    return True
