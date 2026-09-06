"""Tests for metrics aggregation helpers."""

import unittest
from datetime import date, datetime, timezone

from app.services.metrics_service import parse_date_range, segment_for_query_count
from app.services.usage_service import estimate_tokens_from_chars


class MetricsServiceTests(unittest.TestCase):
    def test_parse_date_range_defaults(self) -> None:
        start, end = parse_date_range(None, None, default_days=7)
        self.assertEqual(start.tzinfo, timezone.utc)
        self.assertEqual(end.tzinfo, timezone.utc)
        self.assertLessEqual((end.date() - start.date()).days, 6)

    def test_parse_date_range_explicit(self) -> None:
        start, end = parse_date_range(date(2026, 6, 1), date(2026, 6, 5))
        self.assertEqual(start, datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(end.date(), date(2026, 6, 5))

    def test_segment_for_query_count(self) -> None:
        self.assertEqual(segment_for_query_count(0), "inactive")
        self.assertEqual(segment_for_query_count(5), "occasional")
        self.assertEqual(segment_for_query_count(15), "regular")
        self.assertEqual(segment_for_query_count(30), "power")

    def test_estimate_tokens_from_chars(self) -> None:
        self.assertEqual(estimate_tokens_from_chars(0), 0)
        self.assertEqual(estimate_tokens_from_chars(100), 25)


if __name__ == "__main__":
    unittest.main()
