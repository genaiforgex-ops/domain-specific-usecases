"""Tests for MSA suggestion filtering and apply logic."""

import unittest

from app.services.ai_service import ClauseAnalysis, StubLegalAIService
from app.services.suggestion_service import (
    clause_to_suggestion_dict,
    compile_accepted_suggestions,
    filter_actionable_suggestions,
    is_actionable_suggestion,
)


class SuggestionServiceTests(unittest.TestCase):
    def test_filters_none_risk(self) -> None:
        suggestions = [
            {"risk_flag": "none", "proposed_text": "x", "ai_suggestion": "x"},
            {"risk_flag": "high", "proposed_text": "fix", "ai_suggestion": "fix"},
        ]
        filtered = filter_actionable_suggestions(suggestions)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["risk_flag"], "high")

    def test_actionable_spelling_low(self) -> None:
        s = {
            "risk_flag": "low",
            "category": "spelling",
            "proposed_text": "receive",
            "ai_suggestion": "receive",
        }
        self.assertTrue(is_actionable_suggestion(s))

    def test_compile_replacement(self) -> None:
        base = "Vendor has unlimited liability for all claims."
        suggestions = [
            {
                "order_index": 0,
                "decision": "accept",
                "original_text": "unlimited liability",
                "proposed_text": "limited liability capped at 12 months fees",
                "category": "legal_risk",
            }
        ]
        edited, applied, blocked = compile_accepted_suggestions(base, suggestions)
        self.assertEqual(len(applied), 1)
        self.assertEqual(len(blocked), 0)
        self.assertIn("limited liability capped", edited)
        self.assertNotIn("unlimited liability", edited)

    def test_compile_blocks_missing_excerpt(self) -> None:
        base = "Some contract text."
        suggestions = [
            {
                "order_index": 0,
                "decision": "accept",
                "original_text": "not in document",
                "proposed_text": "replacement",
                "category": "legal_risk",
            }
        ]
        _, applied, blocked = compile_accepted_suggestions(base, suggestions)
        self.assertEqual(len(applied), 0)
        self.assertEqual(len(blocked), 1)

    def test_compile_missing_clause_anchor(self) -> None:
        base = "1. Confidentiality\nKeep secrets.\n\n2. Termination\nEither party may exit."
        suggestions = [
            {
                "order_index": 0,
                "decision": "accept",
                "proposed_text": "DPDP clause body here.",
                "category": "missing_clause",
                "heading": "Data Protection",
                "insert_anchor_hint": "termination",
            }
        ]
        edited, applied, blocked = compile_accepted_suggestions(base, suggestions)
        self.assertEqual(len(applied), 1)
        self.assertIn("inserted after anchor", applied[0].get("apply_note", ""))
        self.assertIn("DPDP clause body", edited)
        idx_dp = edited.find("DPDP clause body")
        idx_term = edited.find("2. Termination")
        self.assertGreater(idx_dp, 0)
        self.assertLess(idx_dp, idx_term)

    def test_stub_review_produces_actionable_only(self) -> None:
        text = (
            "1. Liability\n"
            "Vendor shall have unlimited liability for any and all damages.\n\n"
            "2. Misc\n"
            "The parties agree to cooperate in good faith."
        )
        ai = StubLegalAIService()
        result = ai.review_contract(text, [], contract_type="MSA")
        actionable = filter_actionable_suggestions(
            [clause_to_suggestion_dict(c) for c in result.clauses]
        )
        self.assertGreater(len(actionable), 0)
        self.assertLess(len(actionable), 10)
        for s in actionable:
            self.assertNotEqual(s["risk_flag"], "none")


if __name__ == "__main__":
    unittest.main()
