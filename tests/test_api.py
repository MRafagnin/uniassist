"""Tests for the FastAPI endpoints with mocked chains."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from uniassist import api as api_module
from uniassist import logging_store
from uniassist.rag.chain import ChatResponse, Citation
from uniassist.triage.chain import TriageResponse
from uniassist.triage.schema import TriageResult


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    logging_store.reset_for_tests(db)

    def fake_chat(question: str) -> ChatResponse:
        return ChatResponse(
            answer="answer [1]",
            citations=[
                Citation(
                    n=1,
                    title="UniWiFi",
                    source_url="https://example.com/wifi",
                    source_type="web",
                    file="wifi.md",
                    chunk_index=0,
                )
            ],
            latency_ms=42,
            model="fake-model",
        )

    def fake_triage(text: str) -> TriageResponse:
        return TriageResponse(
            result=TriageResult(
                category="VPN",
                subcategory="drop",
                priority="P2",
                suggested_queue="ICT-Network",
                rationale="user blocked",
                confidence=0.8,
            ),
            latency_ms=10,
            model="fake-model",
            retries=0,
        )

    monkeypatch.setattr(api_module, "rag_answer", fake_chat)
    monkeypatch.setattr(api_module, "triage_call", fake_triage)
    monkeypatch.setattr(api_module, "_refresh_health_cache", lambda: None)

    with TestClient(api_module.app) as c:
        yield c

    logging_store.reset_for_tests()


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "model_chat" in body


def test_chat_endpoint_logs_and_redacts(client):
    r = client.post("/chat", json={"question": "Email student@uni.edu.au about wifi"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("answer")
    assert body["citations"][0]["file"] == "wifi.md"

    rows = logging_store.recent()
    assert len(rows) == 1
    assert rows[0]["endpoint"] == "chat"
    assert "[REDACTED_EMAIL]" in rows[0]["input_redacted"]
    assert json.loads(rows[0]["retrieved_ids"]) == ["wifi.md"]


def test_triage_endpoint_logs_json(client):
    r = client.post("/triage", json={"ticket_text": "VPN drops"})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["category"] == "VPN"

    rows = logging_store.recent()
    assert len(rows) == 1
    assert rows[0]["endpoint"] == "triage"
    assert json.loads(rows[0]["answer"])["category"] == "VPN"


def test_metrics_reflects_calls(client):
    client.post("/chat", json={"question": "wifi help"})
    client.post("/triage", json={"ticket_text": "vpn"})
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["chat"] == 1
    assert body["counts"]["triage"] == 1


def test_cors_header_present(client):
    r = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8501"
