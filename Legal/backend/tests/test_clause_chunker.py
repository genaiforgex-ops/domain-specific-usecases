"""Unit tests for clause-aware chunking.

These pin the behaviour that makes clause citations possible: a provision is never
split mid-sub-clause, and every chunk carries the label its issuer uses.
"""

from __future__ import annotations

from app.services.clause_chunker import (
    ClauseChunk,
    chunk_clauses,
    chunk_key,
    extract_pages,
)

# RBI Master Directions number paragraphs "5.3".
RBI_MD = """
CHAPTER III
CONDUCT REQUIREMENTS

5.1 The RE shall provide a Key Fact Statement (KFS) to the borrower before
execution of the contract.
5.2 The KFS shall be written in a language understood by the borrower and shall
contain the all-inclusive Annual Percentage Rate (APR).
5.3 Cooling-off period
The RE shall provide a cooling-off period during which the borrower may exit the
digital loan by paying the principal and the proportionate APR without any penalty.
The cooling-off period shall not be less than three days for loans having tenor of
seven days or more.
Page 4 of 21
6.1 The RE shall ensure that all loan disbursals are made directly into the bank
account of the borrower.
"""

# Bare Acts number sections "43A."
BARE_ACT = """
CHAPTER IX
PENALTIES AND ADJUDICATION

43A. Compensation for failure to protect data.
Where a body corporate, possessing, dealing or handling any sensitive personal data
in a computer resource which it owns, controls or operates, is negligent in
implementing reasonable security practices, it shall be liable to pay damages by way
of compensation to the person so affected.
44. Penalty for failure to furnish information.
If any person who is required under this Act to furnish any document fails to
furnish the same, he shall be liable to a penalty.
"""

# SEBI circulars number clauses "4.2".
SEBI_CIRCULAR = """
4.1 All mutual funds shall disclose the portfolio on their website.
4.2 Disclosure of commission
(a) Mutual funds shall disclose the commission paid to distributors.
(b) The disclosure shall be made on a half-yearly basis.
(c) The format shall be as specified in Annexure A.
"""

UNSTRUCTURED = """
This charter sets out the rights of customers dealing with regulated entities.

Customers have a right to fair treatment and to be dealt with courteously at all
times, regardless of the channel used.

Customers have a right to privacy and their personal information shall be kept
confidential unless they have offered specific consent.
"""


def _labels(chunks: list[ClauseChunk]) -> list[str | None]:
    return [c.section_label for c in chunks]


def test_rbi_master_direction_paragraph_labels() -> None:
    chunks = chunk_clauses([RBI_MD], doc_type="master_direction", doc_id="LEND-DLD-2025")
    labels = _labels(chunks)
    assert "Para 5.3" in labels
    assert "Para 6.1" in labels

    cooling = next(c for c in chunks if c.section_label == "Para 5.3")
    # The whole provision stays together, including the sentence after the heading.
    assert "cooling-off period" in cooling.text
    assert "three days" in cooling.text
    # Chapter heading is carried down as parent context.
    assert cooling.parent_heading is not None
    assert "CONDUCT REQUIREMENTS" in (cooling.parent_heading or "")


def test_page_furniture_is_dropped() -> None:
    chunks = chunk_clauses([RBI_MD], doc_type="master_direction")
    assert all("Page 4 of 21" not in c.text for c in chunks)


def test_bare_act_section_labels() -> None:
    chunks = chunk_clauses([BARE_ACT], doc_type="bare_act", doc_id="DP-ITACT-2000")
    labels = _labels(chunks)
    assert "Section 43A" in labels
    assert "Section 44" in labels

    s43a = next(c for c in chunks if c.section_label == "Section 43A")
    assert "reasonable security practices" in s43a.text
    # Section 44's text must not bleed into 43A.
    assert "Penalty for failure" not in s43a.text


def test_sebi_clause_labels_and_subclauses_stay_together() -> None:
    chunks = chunk_clauses([SEBI_CIRCULAR], doc_type="circular", doc_id="INV-MF-MASTERCIRC-2026")
    labels = _labels(chunks)
    assert "Clause 4.2" in labels

    clause = next(c for c in chunks if c.section_label == "Clause 4.2")
    # All three lettered sub-clauses belong to the same citable provision.
    for marker in ("(a)", "(b)", "(c)"):
        assert marker in clause.text


def test_pages_are_tracked_across_a_multi_page_document() -> None:
    chunks = chunk_clauses(["1.1 First provision text here.", "2.1 Second provision text."],
                           doc_type="master_direction")
    pages = {c.section_label: c.page for c in chunks}
    assert pages["Para 1.1"] == 1
    assert pages["Para 2.1"] == 2


def test_unstructured_text_falls_back_to_paragraph_packing() -> None:
    chunks = chunk_clauses([UNSTRUCTURED], doc_type="charter")
    assert chunks, "fallback must still produce chunks"
    assert all(c.section_label is None for c in chunks)
    assert "right to fair treatment" in " ".join(c.text for c in chunks)


def test_oversized_provision_splits_with_parent_header_repeated() -> None:
    body = "\n".join(f"({chr(97 + i)}) " + ("obligation text " * 60) for i in range(12))
    long_provision = f"7.1 Reporting obligations\n{body}"
    chunks = chunk_clauses([long_provision], doc_type="master_direction")

    assert len(chunks) > 1
    # Every part is still attributable to the parent provision.
    assert all("Para 7.1" in (c.section_label or "") for c in chunks)
    assert all("Reporting obligations" in c.text for c in chunks)
    # Parts are numbered so a citation is unambiguous.
    assert any("(1/" in (c.section_label or "") for c in chunks)


def test_short_provision_keeps_its_own_label() -> None:
    """A one-line commencement clause must stay citable rather than being absorbed."""
    text = (
        "1.1 These Directions shall come into force on May 8, 2025.\n"
        "1.2 These Directions shall apply to all Regulated Entities as specified in "
        "paragraph 2 below, including banks and non-banking financial companies."
    )
    chunks = chunk_clauses([text], doc_type="directions")
    labels = _labels(chunks)
    assert "Para 1.1" in labels
    assert "Para 1.2" in labels

    commencement = next(c for c in chunks if c.section_label == "Para 1.1")
    assert "May 8, 2025" in commencement.text
    # It must not have swallowed the next provision.
    assert "Regulated Entities" not in commencement.text


def test_ordinals_are_sequential_and_unique() -> None:
    chunks = chunk_clauses([RBI_MD], doc_type="master_direction")
    ordinals = [c.ordinal for c in chunks]
    assert ordinals == sorted(ordinals)
    assert len(set(ordinals)) == len(ordinals)


def test_token_count_and_chunk_key() -> None:
    chunk = ClauseChunk(text="x" * 400, page=1, ordinal=3, section_label="Para 5.3")
    assert chunk.token_count == 100
    assert chunk_key("LEND-DLD-2025", chunk) == "LEND-DLD-2025:para-5-3"

    unlabelled = ClauseChunk(text="y", page=1, ordinal=7)
    assert chunk_key("X", unlabelled) == "X:chunk-7"


def test_extract_pages_reads_plain_text_and_html() -> None:
    assert extract_pages(b"hello world", "a.txt") == ["hello world"]
    html = b"<html><body><nav>skip</nav><p>Clause text</p><script>x=1</script></body></html>"
    pages = extract_pages(html, "a.html")
    assert "Clause text" in pages[0]
    assert "skip" not in pages[0]
    assert "x=1" not in pages[0]
