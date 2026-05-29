import pytest
from pydantic import ValidationError

from uniassist.triage.schema import TriageResult


def test_valid_triage_result():
    r = TriageResult(
        category="VPN",
        subcategory="disconnect every 10 minutes",
        priority="P2",
        suggested_queue="ICT-Network",
        rationale="User cannot work; VPN keeps dropping.",
        confidence=0.82,
    )
    assert r.category == "VPN"
    assert r.priority == "P2"


def test_invalid_priority_rejected():
    with pytest.raises(ValidationError):
        TriageResult(
            category="VPN",
            subcategory="x",
            priority="URGENT",  # type: ignore[arg-type]
            suggested_queue="ICT-Network",
            rationale="x",
            confidence=0.5,
        )


def test_invalid_category_rejected():
    with pytest.raises(ValidationError):
        TriageResult(
            category="Plumbing",  # type: ignore[arg-type]
            subcategory="x",
            priority="P4",
            suggested_queue="Facilities",
            rationale="x",
            confidence=0.5,
        )


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        TriageResult(
            category="WiFi",
            subcategory="x",
            priority="P3",
            suggested_queue="ICT-Network",
            rationale="x",
            confidence=1.5,
        )
