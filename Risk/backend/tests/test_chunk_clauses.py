from app.scripts.regulation_ingest.chunk_clauses import (
    build_clause_ref,
    chunk_paragraphs,
    derive_tags,
    detect_context,
)


def test_detect_context_chapter_section_annexure():
    assert detect_context("Chapter III – Outsourcing of Financial Services") == "ChIII"
    assert detect_context("II. MEASURES TO STRENGTHEN THE CONDUCT") == "SII"
    assert detect_context("ANNEXURE H – Principles for Outsourcing") == "AnxH"
    assert detect_context("Not a heading at all.") is None


def test_chunk_paragraphs_groups_subitems_under_parent():
    blocks = [
        {"page_no": 12, "text": "Chapter III – Outsourcing of Financial Services"},
        {"page_no": 12, "text": "B. Activities that shall not be outsourced"},
        {"page_no": 12, "text": "15. An NBFC shall not outsource core management functions"},
        {"page_no": 12, "text": "(i) Internal Audit"},
        {"page_no": 13, "text": "(ii) strategic and compliance functions."},
        {"page_no": 13, "text": "16. An NBFC desiring to outsource shall not require prior approval."},
    ]
    chunks = chunk_paragraphs(blocks)

    assert len(chunks) == 2
    first, second = chunks
    assert first["context"] == "ChIII"
    assert first["para_no"] == "15"
    assert first["page_no"] == 12  # starting page, even though sub-item spills to p.13
    assert "Internal Audit" in first["text"]
    assert "strategic and compliance" in first["text"]
    assert second["para_no"] == "16"
    assert second["page_no"] == 13


def test_chunk_paragraphs_drops_pre_first_paragraph_preamble():
    blocks = [
        {"page_no": 1, "text": "In exercise of the powers conferred by Section 45L..."},
        {"page_no": 4, "text": "1. These Directions shall be called the RBI Directions, 2025."},
    ]
    chunks = chunk_paragraphs(blocks)
    assert len(chunks) == 1
    assert chunks[0]["para_no"] == "1"


def test_build_clause_ref():
    chunk = {"context": "ChIII", "para_no": "15"}
    assert build_clause_ref("RBI-NBFC-2025", chunk) == "RBI-NBFC-2025-ChIII-P15"


def test_derive_tags():
    assert derive_tags("An NBFC shall not outsource core management functions") == "prohibited"
    assert derive_tags("cloud computing services and data centre operations") == "it"
    assert derive_tags("KYC norms for opening deposit accounts") == "financial"
    assert derive_tags("Housekeeping and catering services are excluded.") == "general"
