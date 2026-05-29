"""Triage chain: ticket text -> TriageResult JSON."""
from __future__ import annotations

import json
import time

from pydantic import BaseModel, ValidationError

from uniassist.config import settings
from uniassist.rag.prompts import TRIAGE_SYSTEM
from uniassist.triage.schema import TriageResult


class TriageResponse(BaseModel):
    result: TriageResult
    latency_ms: int
    model: str
    retries: int


_llm = None


def _build_llm():
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.model_chat,
        base_url=settings.ollama_host,
        temperature=0,
        format="json",
    )


def _llm_invoke(messages: list):
    global _llm
    if _llm is None:
        _llm = _build_llm()
    return _llm.invoke(messages)


def _parse(raw: str) -> TriageResult:
    data = json.loads(raw)
    return TriageResult.model_validate(data)


def triage(ticket_text: str) -> TriageResponse:
    from langchain_core.messages import HumanMessage, SystemMessage

    t0 = time.perf_counter()
    messages = [
        SystemMessage(content=TRIAGE_SYSTEM),
        HumanMessage(content=ticket_text),
    ]

    last_err: str = ""
    for attempt in range(2):
        try:
            result_msg = _llm_invoke(messages)
            raw = getattr(result_msg, "content", str(result_msg))
            result = _parse(raw)
            return TriageResponse(
                result=result,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                model=settings.model_chat,
                retries=attempt,
            )
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            continue

    fallback = TriageResult(
        category="Other",
        subcategory="unparseable",
        priority="P3",
        suggested_queue="ICT-Service-Desk",
        rationale=f"parse_failed: {last_err}",
        confidence=0.0,
    )
    return TriageResponse(
        result=fallback,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        model=settings.model_chat,
        retries=2,
    )
