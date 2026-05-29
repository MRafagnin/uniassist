"""Tests for the SQLite query log."""
from __future__ import annotations

import json

import pytest

from uniassist import logging_store


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    logging_store.reset_for_tests(db)
    yield db
    logging_store.reset_for_tests()


def test_init_and_log_roundtrip(temp_db):
    logging_store.init_db()
    rid = logging_store.log_query(
        endpoint="chat",
        input_redacted="hello",
        retrieved_ids=["a.md", "b.md"],
        answer="hi",
        latency_ms=120,
        model="m",
    )
    assert rid >= 1
    rows = logging_store.recent()
    assert len(rows) == 1
    assert rows[0]["endpoint"] == "chat"
    assert json.loads(rows[0]["retrieved_ids"]) == ["a.md", "b.md"]


def test_summary_percentiles_and_categories(temp_db):
    logging_store.init_db()
    latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    for ms in latencies:
        logging_store.log_query(
            endpoint="chat",
            input_redacted="q",
            answer="a",
            latency_ms=ms,
            model="m",
        )
    for cat in ["VPN", "VPN", "WiFi"]:
        logging_store.log_query(
            endpoint="triage",
            input_redacted="t",
            answer=json.dumps({"category": cat, "priority": "P3"}),
            latency_ms=5,
            model="m",
        )
    s = logging_store.summary()
    assert s["counts"] == {"chat": 10, "triage": 3}
    chat_lat = s["latency_ms"]["chat"]
    assert chat_lat["n"] == 10
    # P50 of 10..100 = 55.0; P95 = 95.5
    assert chat_lat["p50"] == pytest.approx(55.0)
    assert chat_lat["p95"] == pytest.approx(95.5)
    cats = dict(s["top_categories"])
    assert cats["VPN"] == 2
    assert cats["WiFi"] == 1
