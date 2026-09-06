"""Retrieval-quality eval for the regulatory corpus.

Turns "the bot feels vague" into four numbers you can move:

  retrieval hit-rate  — is the correct clause in the top-k?
  citation accuracy   — is the correct clause ranked #1?
  precision           — did the right document dominate the results?
  staleness           — did any answer surface superseded law? (target: 0)

Needs a live Postgres corpus and real embedding calls, so it is skipped unless
RUN_RAG_EVAL=1. Cases naming a document that has not been ingested yet are counted
as skipped, not failed — the eval set describes the target corpus, and a document
the legal team has not uploaded is not a retrieval bug.

    docker exec -e RUN_RAG_EVAL=1 legalos-backend python -m pytest tests/eval -q -s
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.eval

EVAL_SET = Path(__file__).with_name("regulatory_eval_set.yaml")
TOP_K = 8

_ENABLED = os.getenv("RUN_RAG_EVAL") == "1"


def _load_cases() -> list[dict]:
    """Parse the eval set. Uses PyYAML when present, else a tiny list parser."""
    text = EVAL_SET.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return list(yaml.safe_load(text) or [])
    except ImportError:
        pass

    cases: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.split(" #")[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("- "):
            if current:
                cases.append(current)
            current = {}
            line = "  " + line[2:]
        if current is None or ":" not in line:
            continue
        key, _, value = line.strip().partition(":")
        value = value.strip().strip("'\"")
        if value.startswith("["):
            current[key.strip()] = [
                v.strip() for v in value.strip("[]").split(",") if v.strip()
            ]
        else:
            current[key.strip()] = value
    if current:
        cases.append(current)
    return cases


@pytest.mark.skipif(not _ENABLED, reason="set RUN_RAG_EVAL=1 to run the retrieval eval")
def test_regulatory_retrieval_quality() -> None:
    from app.database import SessionLocal
    from app.models.regulatory_corpus import STATUS_INGESTED, RegulatoryDocument
    from app.services.regulatory_rag_service import search_regulatory
    from app.services.regulatory_router import route_query
    from sqlalchemy import select

    cases = _load_cases()
    assert cases, "eval set is empty"

    db = SessionLocal()
    try:
        ingested = {
            d.doc_id
            for d in db.execute(
                select(RegulatoryDocument).where(
                    RegulatoryDocument.status == STATUS_INGESTED
                )
            )
            .scalars()
            .all()
        }

        hits = top1 = evaluated = skipped = stale = 0
        precision_total = 0.0
        failures: list[str] = []

        for case in cases:
            doc_id = str(case.get("doc_id") or "")
            if doc_id not in ingested:
                skipped += 1
                continue

            question = str(case["question"])
            pattern = re.compile(str(case.get("expect_section") or "."))
            route = route_query(question)
            results = search_regulatory(
                db,
                question,
                domains=route.domains or None,
                include_superseded=route.include_superseded,
                top_k=TOP_K,
            )
            evaluated += 1

            matched = [
                r
                for r in results
                if r.doc_id == doc_id and pattern.search(r.section_label or "")
            ]
            if matched:
                hits += 1
            else:
                failures.append(
                    f"MISS {doc_id} {case.get('expect_section')} :: {question!r} -> "
                    + ", ".join(f"{r.doc_id}/{r.section_label}" for r in results[:3])
                )

            if results and results[0].doc_id == doc_id and pattern.search(
                results[0].section_label or ""
            ):
                top1 += 1

            if results:
                precision_total += sum(1 for r in results if r.doc_id == doc_id) / len(
                    results
                )
            # Superseded law must never reach an answer unless asked for.
            if not route.include_superseded:
                stale += sum(1 for r in results if r.superseded_by)

        if not evaluated:
            # Nothing to measure is not a quality regression — say so honestly.
            pytest.skip(
                f"No eval case matches an ingested document ({skipped} case(s) waiting). "
                "Load the P1 documents via the Regulatory Corpus page or "
                "scripts/sync_regulatory_to_rag.py, then re-run."
            )

        hit_rate = hits / evaluated
        citation_accuracy = top1 / evaluated
        precision = precision_total / evaluated

        print(
            f"\n─── regulatory retrieval eval ───────────────────────────────\n"
            f"cases evaluated     : {evaluated} (skipped {skipped}, not ingested)\n"
            f"hit-rate@{TOP_K}        : {hit_rate:.0%}  ({hits}/{evaluated})\n"
            f"citation accuracy   : {citation_accuracy:.0%}  (correct clause ranked #1)\n"
            f"doc precision       : {precision:.0%}\n"
            f"staleness           : {stale}  (superseded clauses returned; target 0)\n"
            + ("\n".join(failures) + "\n" if failures else "")
            + "─────────────────────────────────────────────────────────────"
        )

        # Staleness is a correctness guarantee, not a quality metric.
        assert stale == 0, f"{stale} superseded clause(s) were returned"
        assert hit_rate >= 0.8, f"hit-rate@{TOP_K} regressed to {hit_rate:.0%}"
    finally:
        db.close()


def test_eval_set_is_well_formed() -> None:
    """Always runs: a malformed eval set must fail loudly, not silently skip."""
    cases = _load_cases()
    assert len(cases) >= 10

    from app.services.regulatory_manifest import load_manifest

    manifest = load_manifest()
    for case in cases:
        assert case.get("question"), f"case without a question: {case}"
        doc_id = case.get("doc_id")
        assert doc_id in manifest, f"{doc_id} is not a manifest doc_id"
        re.compile(str(case.get("expect_section") or "."))
