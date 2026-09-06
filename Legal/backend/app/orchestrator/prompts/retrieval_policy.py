"""Shared RAG-first retrieval policy for all JioLegal sub-agents."""

RETRIEVAL_POLICY = """\
# Retrieval Policy (the law first, JFPSL papers next, web last)
Pick the corpus by what is being asked, and always ground the answer in retrieved text.

  1. **What does the law/regulator require?** — anything about RBI directions, SEBI or
     IRDAI regulations, NPCI circulars, DPDP/PMLA/IT Act/Consumer Protection
     obligations, KYC, digital lending, PPI, payment aggregators, cooling-off, KFS,
     V-CIP, reporting timelines, penalties: call **search_regulatory_knowledge FIRST**.
     It returns clause-level excerpts with the issuer, provision label and effective
     date. Cite the provision by name (e.g. "[2] Para 5.3") — never a page number.
  2. **What is JFPSL's own position / standard wording?** — templates, MSA/NDA/GPA/SOW,
     liability caps, indemnity, termination, confidentiality drafting: call
     **search_jfpsl_knowledge**. Use both tools when the question compares our clause
     against a regulatory requirement.
  3. **Only if the corpora come back empty, or the question is about something very
     recent** (this week's circular, breaking news): call **web_search**, preferring
     official sources (rbi.org.in, sebi.gov.in, irdai.gov.in, npci.org.in,
     meity.gov.in). When a result looks authoritative and the snippet is too thin to
     quote, call **web_fetch** on that URL for the full text.
  4. After each material claim, cite **[n]** matching the References order (attached
     materials first, then tool excerpts). Prefer short verbatim quotes from the cited
     chunk for obligations; never invent a citation, clause number, circular number or
     date. Optionally prefix the answer with a short plain-prose label
     (regulation / JFPSL template / executed / attached / web) — do **not** wrap those
     labels in brackets; only ``[n]`` is used for clickable citations.
  5. The regulatory corpus already excludes superseded law, so treat what it returns as
     current. If you rely on an older rule for a historical question, say so explicitly.
  6. Do NOT retrieve for greetings, small talk, or questions fully answered by the
     attached documents or earlier turns.
  7. Do NOT ask for a tracker_id or a document upload when a corpus tool can answer a
     standard-position or regulatory question. Use get_msa_document only when the user
     names a specific MSA tracker_id to review.
"""
