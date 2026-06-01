"""Thin httpx wrapper around the UniAssist FastAPI."""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

import httpx

API_BASE = os.getenv("UNIASSIST_API", "http://localhost:8000")
_TIMEOUT = httpx.Timeout(180.0, connect=5.0)


class APIError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=_TIMEOUT)


def _raise(r: httpx.Response) -> Any:
    if r.status_code // 100 != 2:
        raise APIError(r.status_code, r.text)
    return r.json()


def healthz() -> dict[str, Any]:
    with _client() as c:
        return _raise(c.get("/healthz"))


def chat(question: str) -> dict[str, Any]:
    with _client() as c:
        return _raise(c.post("/chat", json={"question": question}))


def chat_stream(question: str) -> Iterator[dict[str, Any]]:
    """Yield NDJSON events from /chat/stream."""
    with httpx.Client(base_url=API_BASE, timeout=_TIMEOUT) as c:
        with c.stream("POST", "/chat/stream", json={"question": question}) as r:
            if r.status_code // 100 != 2:
                body = r.read().decode("utf-8", errors="replace")
                raise APIError(r.status_code, body)
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def triage(ticket_text: str) -> dict[str, Any]:
    with _client() as c:
        return _raise(c.post("/triage", json={"ticket_text": ticket_text}))


def metrics() -> dict[str, Any]:
    with _client() as c:
        return _raise(c.get("/metrics"))


def recent(limit: int = 20) -> list[dict[str, Any]]:
    with _client() as c:
        return _raise(c.get("/recent", params={"limit": limit}))
