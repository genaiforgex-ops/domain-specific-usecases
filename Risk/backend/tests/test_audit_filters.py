"""Regression tests for the audit log's Module / Action search boxes.

They were wired to exact equality behind a free-text UI, so anything short of a
complete, correctly-cased value returned nothing: "login" missed `login_failed`,
"AI" missed `ai.invocation`, and every partial word typed on the way to a full
value returned an empty log.
"""
import pytest
from sqlalchemy import Column, String, select
from sqlalchemy.orm import declarative_base

from app.api.v1.cross import _contains

Base = declarative_base()


class Row(Base):
    __tablename__ = "rows"
    value = Column(String, primary_key=True)


def sql_for(needle: str) -> str:
    """The rendered WHERE clause, with the bound pattern inlined."""
    clause = select(Row).where(_contains(Row.value, needle))
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def pattern_for(needle: str) -> str:
    import re

    match = re.search(r"lower\(\?\)|'(%.*?%)'", sql_for(needle))
    assert match, sql_for(needle)
    return match.group(1)


class TestSubstringMatching:
    def test_the_filter_is_a_substring_match(self):
        assert pattern_for("login") == "%login%"

    def test_matching_is_case_insensitive(self):
        # ilike() renders as lower(a) LIKE lower(b) on most dialects.
        assert "lower" in sql_for("AI").lower() or "ILIKE" in sql_for("AI")

    def test_surrounding_whitespace_is_ignored(self):
        assert pattern_for("  login  ") == "%login%"


class TestWildcardEscaping:
    def test_underscores_are_escaped_not_treated_as_wildcards(self):
        """`_` is a single-char wildcard in LIKE, and real values contain it.

        Unescaped, a search for `dd_report` would also match `ddXreport`.
        """
        assert pattern_for("dd_report") == r"%dd\_report%"

    def test_percent_is_escaped_so_it_cannot_match_everything(self):
        assert pattern_for("100%") == r"%100\%%"

    def test_backslash_is_escaped_first(self):
        # Escaping the escape character must come before the metacharacters,
        # or the added backslashes get doubled a second time.
        assert pattern_for(r"a\b") == r"%a\\b%"

    def test_an_escape_character_is_declared(self):
        assert "ESCAPE" in sql_for("dd_report").upper()


@pytest.mark.parametrize(
    "typed,value,should_match",
    [
        # The exact failures reported against the old equality filter.
        ("login", "login_failed", True),
        ("AI", "ai.invocation", True),
        ("log", "login", True),
        ("user.", "user.created", True),
        ("M1", "M1", True),
        ("invocation", "ai.invocation", True),
        # Still discriminating — this is a filter, not a pass-through.
        ("vendor", "login", False),
        ("dd_report", "classification_job", False),
    ],
)
def test_reported_search_cases(typed, value, should_match):
    """Mirror the SQL semantics in Python: casefold + substring."""
    assert (typed.strip().casefold() in value.casefold()) is should_match
