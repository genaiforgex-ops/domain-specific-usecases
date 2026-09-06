import json

import pytest

from app.services.scoring_service import ScoringService, FACTOR_KEYS


def test_compute_inherent_deterministic():
    svc = ScoringService.__new__(ScoringService)
    weights = {k: 1.0 for k in FACTOR_KEYS}
    intake = {k: 3 for k in FACTOR_KEYS}
    score1, _ = svc._compute_inherent(intake, weights)
    score2, _ = svc._compute_inherent(intake, weights)
    assert score1 == score2
    assert 1 <= score1 <= 25


def test_band_mapping():
    svc = ScoringService.__new__(ScoringService)
    assert svc._band(3) == "Low"
    assert svc._band(10) == "Medium"
    assert svc._band(18) == "High"
