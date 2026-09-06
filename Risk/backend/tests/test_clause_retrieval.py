from app.services.clause_retrieval import SKIP_THRESHOLD, select_relevant_clauses


def _clause(idx: int, text: str) -> dict:
    return {"id": f"c{idx}", "clause_ref": f"REF-{idx}", "text": text, "tags": "general", "regulator": "RBI"}


def test_small_corpus_returned_unfiltered():
    clauses = [_clause(i, f"clause body {i}") for i in range(SKIP_THRESHOLD)]
    assert select_relevant_clauses("anything at all", clauses, k=3) == clauses


def test_large_corpus_ranks_by_keyword_overlap():
    clauses = [_clause(i, "housekeeping catering janitorial premises security") for i in range(SKIP_THRESHOLD + 10)]
    clauses[7] = _clause(7, "cloud computing services data centre disaster recovery plan")
    clauses[20] = _clause(20, "cloud computing services security operations centre SOC")

    result = select_relevant_clauses(
        "Vendor will host our platform on their cloud computing infrastructure with a disaster recovery plan.",
        clauses,
        k=2,
    )

    result_ids = {c["id"] for c in result}
    assert result_ids == {"c7", "c20"}


def test_no_lexical_overlap_falls_back_to_first_k():
    clauses = [_clause(i, "zzz qqq xxx yyy www") for i in range(SKIP_THRESHOLD + 1)]
    result = select_relevant_clauses("unrelated query terms entirely", clauses, k=3)
    assert [c["id"] for c in result] == ["c0", "c1", "c2"]


def test_empty_query_falls_back_to_first_k():
    clauses = [_clause(i, "some text") for i in range(SKIP_THRESHOLD + 1)]
    result = select_relevant_clauses("   ", clauses, k=4)
    assert [c["id"] for c in result] == ["c0", "c1", "c2", "c3"]
