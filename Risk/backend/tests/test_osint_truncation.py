"""Regression tests for the empty-DD-report bug.

A vendor DD run intermittently produced a blank report tagged
`unparseable_model_response`. The cause was `max_output_tokens=8000`: on a
thinking model that cap covers reasoning tokens and every Google-Search
grounding round, not just the final JSON, so the model ran out of budget before
writing the audit. The API then returns finish_reason=MAX_TOKENS with
`response.text` EMPTY — not a partial object — so there was nothing for
_repair_json to salvage and the failure was misreported as malformed JSON.

Measured against the live API on the vendor that was failing: ~3.5k thinking +
~5.5k answer tokens, i.e. ~9k needed against an 8k cap.
"""
from types import SimpleNamespace

from app.adapters.osint.gemini_osint import (
    _MAX_OUTPUT_TOKENS,
    _extract_json,
    _hit_output_limit,
    _repair_json,
)


def _response(*finish_reasons):
    return SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason=r) for r in finish_reasons]
    )


class TestOutputLimitDetection:
    def test_max_tokens_is_reported_as_truncation(self):
        assert _hit_output_limit(_response("FinishReason.MAX_TOKENS")) is True

    def test_a_normal_stop_is_not_truncation(self):
        assert _hit_output_limit(_response("FinishReason.STOP")) is False

    def test_one_truncated_candidate_is_enough(self):
        assert _hit_output_limit(_response("FinishReason.STOP", "FinishReason.MAX_TOKENS")) is True

    def test_a_response_without_candidates_is_not_truncation(self):
        assert _hit_output_limit(_response()) is False
        assert _hit_output_limit(SimpleNamespace()) is False

    def test_detection_survives_an_unexpected_finish_reason_shape(self):
        # Checked by name, so an SDK change degrades to "not truncated" rather
        # than raising inside the error-handling path.
        assert _hit_output_limit(_response(None)) is False
        assert _hit_output_limit(_response(3)) is False


class TestTruncatedResponseParsing:
    def test_an_empty_response_yields_no_audit(self):
        """What MAX_TOKENS actually returns — repair has nothing to work with."""
        assert _extract_json("") is None

    def test_a_partially_written_object_is_still_repaired(self):
        # The salvage path stays useful for a response cut off mid-write.
        parsed = _extract_json('{"business_name": "Acme Ltd", "risk": {"score": 40')
        assert parsed is not None
        assert parsed["business_name"] == "Acme Ltd"
        assert parsed["risk"]["score"] == 40

    def test_repair_closes_an_unterminated_string(self):
        assert _extract_json('{"business_name": "Acme') == {"business_name": "Acme"}

    def test_fenced_json_is_unwrapped(self):
        assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_genuinely_malformed_output_still_fails(self):
        # Prose with no JSON object must not be coerced into a fake audit.
        assert _extract_json("I could not complete this audit.") is None
        assert _repair_json("") == ""


def test_output_budget_leaves_room_for_thinking_and_grounding():
    """The regression guard: 8000 was not enough for a real grounded audit."""
    assert _MAX_OUTPUT_TOKENS >= 16000
