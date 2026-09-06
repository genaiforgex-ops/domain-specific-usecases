"""Lightweight, dependency-free keyword retrieval to narrow a large clause
corpus (e.g. SEBI's full master circular, ingested whole — see
app/scripts/regulation_ingest/) down to the handful most relevant to a given
assessment text before it goes into an LLM prompt.

Not semantic search — no embeddings, no network call, deterministic and
cheap enough to run inline on every classify call. Good enough because
compliance/legal text tends to share vocabulary with the vendor clauses it
governs ("cloud", "IT", "KYC", "data centre", "audit"...). Below
SKIP_THRESHOLD this is a no-op, so today's small hand-curated RBI/SEBI sets
keep getting every clause sent to the LLM exactly as before — only kicks in
once a corpus is large enough that dumping all of it would bloat the prompt.

Swap for embedding-based retrieval later if keyword overlap proves
insufficient; google-genai (already a dependency for the LLM adapter)
supports embed_content without adding new infra.
"""
import re

SKIP_THRESHOLD = 15

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "by", "with",
    "is", "are", "be", "shall", "any", "such", "this", "that", "as", "its",
    "it", "if", "not", "may", "from", "at", "which", "who", "their", "all",
    "other", "than", "into", "under", "per", "i", "ii", "iii", "shall",
})
_TOKEN_RE = re.compile(r"[a-z]{3,}")


def _tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


def select_relevant_clauses(text: str, clauses: list[dict], k: int) -> list[dict]:
    """Return at most `k` clauses ranked by token overlap with `text`.

    `k <= 0` disables narrowing entirely — every clause is sent to the model.
    This is the intended mode now that the active library is curated (via
    archiving) small enough to fit in the prompt: the word-overlap filter was
    dropping the correct clause whenever it happened to use different wording
    than the assessment text. Returns `clauses` unchanged if there are
    SKIP_THRESHOLD or fewer, regardless of `k`."""
    if k <= 0 or len(clauses) <= SKIP_THRESHOLD:
        return clauses

    query_tokens = _tokenize(text)
    if not query_tokens:
        return clauses[:k]

    scored = []
    for idx, clause in enumerate(clauses):
        clause_tokens = _tokenize(clause.get("text", ""))
        overlap = len(query_tokens & clause_tokens)
        # -idx as secondary key: with reverse=True this prefers the
        # earlier-listed clause on a tie, keeping ranking deterministic.
        scored.append((overlap, -idx, clause))

    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    top = [c for score, _, c in scored[:k] if score > 0]
    if not top:
        # nothing overlapped lexically at all — fall back to the first k so
        # the LLM still gets something to classify against rather than
        # nothing, rather than silently degrading to an empty clause list.
        return clauses[:k]
    return top
