"""Tests for the triage chain with a mocked Ollama call."""
from __future__ import annotations

import json

from uniassist.triage import chain as triage_chain


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


def _valid_json() -> str:
    return json.dumps(
        {
            "category": "VPN",
            "subcategory": "GlobalProtect disconnect",
            "priority": "P2",
            "suggested_queue": "ICT-Network",
            "rationale": "User cannot work; VPN drops repeatedly.",
            "confidence": 0.78,
        }
    )


def test_triage_valid_json(monkeypatch):
    monkeypatch.setattr(triage_chain, "_llm_invoke", lambda m: _Msg(_valid_json()))
    resp = triage_chain.triage("VPN drops every 10 min")
    assert resp.result.category == "VPN"
    assert resp.result.priority == "P2"
    assert resp.retries == 0
    assert resp.latency_ms >= 0


def test_triage_retries_then_recovers(monkeypatch):
    calls = {"n": 0}

    def fake(_m):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Msg("not json at all")
        return _Msg(_valid_json())

    monkeypatch.setattr(triage_chain, "_llm_invoke", fake)
    resp = triage_chain.triage("anything")
    assert resp.result.category == "VPN"
    assert resp.retries == 1


def test_triage_fallback_on_repeated_failure(monkeypatch):
    monkeypatch.setattr(triage_chain, "_llm_invoke", lambda m: _Msg("totally invalid"))
    resp = triage_chain.triage("anything")
    assert resp.result.category == "Other"
    assert resp.result.priority == "P3"
    assert resp.result.confidence == 0.0
    assert resp.retries == 2
    assert "parse_failed" in resp.result.rationale
