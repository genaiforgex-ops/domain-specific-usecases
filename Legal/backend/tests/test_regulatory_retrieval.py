"""Unit tests for retrieval fusion and query routing (no DB, no network)."""

from __future__ import annotations

from app.services.regulatory_rag_service import fuse_rankings
from app.services.regulatory_router import route_query


# ── Reciprocal Rank Fusion ──────────────────────────────────────────────────
def test_agreeing_channels_rank_first() -> None:
    keyword = [10, 20, 30]
    semantic = [10, 40, 50]
    ranked = fuse_rankings([keyword, semantic])
    assert ranked[0][0] == 10, "a chunk both channels rank first must win"


def test_keyword_only_hit_still_survives() -> None:
    """Exact-term hits ("Section 43A") must not be swamped by vector results."""
    keyword = [99]
    semantic = [1, 2, 3, 4, 5, 6, 7, 8]
    ranked = fuse_rankings([keyword, semantic])
    ids = [cid for cid, _ in ranked]
    assert 99 in ids
    # Rank 1 in one channel beats rank 1 in the other only on ties; it must at
    # least outrank everything below the other channel's top hit.
    assert ids.index(99) <= 1


def test_vertex_boost_breaks_a_tie_without_overriding_rank() -> None:
    # Two chunks in symmetric positions: 1st in one channel, 2nd in the other.
    keyword = [1, 2]
    semantic = [2, 1]
    doc_map = {1: "DOC-A", 2: "DOC-B"}

    plain = fuse_rankings([keyword, semantic], doc_id_by_chunk=doc_map)
    assert plain[0][1] == plain[1][1], "symmetric ranks should tie before boosts"

    boosted = fuse_rankings(
        [keyword, semantic], doc_id_by_chunk=doc_map, vertex_scores={"DOC-B": 0.9}
    )
    assert boosted[0][0] == 2, "the Vertex-surfaced document should win the tie"

    # A boost must not lift a poorly ranked chunk over a clearly better one.
    strong = fuse_rankings(
        [[7], [7]],
        doc_id_by_chunk={7: "DOC-A", 8: "DOC-B"},
        vertex_scores={"DOC-B": 1.0},
    )
    assert strong[0][0] == 7


def test_p1_priority_breaks_a_tie() -> None:
    ranked = fuse_rankings(
        [[1, 2], [2, 1]],
        doc_id_by_chunk={1: "DOC-P1", 2: "DOC-P3"},
        priority_by_doc={"DOC-P1": "P1", "DOC-P3": "P3"},
    )
    assert ranked[0][0] == 1


def test_empty_channels_fuse_to_nothing() -> None:
    assert fuse_rankings([[], []]) == []


# ── Query routing ───────────────────────────────────────────────────────────
def test_regulatory_question_routes_to_the_law_corpus() -> None:
    route = route_query("what is the cooling-off period under RBI digital lending rules")
    assert route.use_regulatory is True
    assert "lending_credit" in route.domains
    assert route.include_superseded is False


def test_kyc_question_routes_to_aml_domain() -> None:
    route = route_query("is V-CIP mandatory for re-KYC of existing customers?")
    assert "aml_kyc" in route.domains


def test_privacy_question_routes_to_data_domain_and_official_hosts() -> None:
    route = route_query("what consent does the DPDP Act require from a data principal")
    assert "data_privacy_cyber" in route.domains
    assert any(h in route.site_hosts for h in ("meity.gov.in", "indiacode.nic.in"))


def test_internal_question_routes_to_jfpsl() -> None:
    route = route_query("what is our standard liability cap in the JFPSL MSA template?")
    assert route.use_jfpsl is True


def test_comparison_question_uses_both_corpora() -> None:
    route = route_query(
        "does our MSA template's data protection clause satisfy the DPDP Act requirements?"
    )
    assert route.use_jfpsl is True
    assert route.use_regulatory is True


def test_historical_question_allows_superseded_law() -> None:
    for query in (
        "what was the cooling-off rule before 2025",
        "what did the repealed digital lending guidelines say",
        "the erstwhile KYC direction requirement",
    ):
        assert route_query(query).include_superseded is True, query


def test_recency_question_asks_for_web() -> None:
    route = route_query("any update on UPI circulars issued this month?")
    assert route.needs_web is True
    assert route.site_hosts, "recency queries should be scoped to official hosts"


def test_empty_query_selects_nothing() -> None:
    route = route_query("   ")
    assert route.use_regulatory is False


def test_route_summary_is_human_readable() -> None:
    summary = route_query("RBI KYC master direction V-CIP").summary
    assert "regulatory corpus" in summary
