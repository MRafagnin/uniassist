"""LCEL RAG chain: retrieve -> format -> chat -> cited answer."""
from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel

from uniassist.config import settings
from uniassist.guardrails import is_in_scope
from uniassist.rag.prompts import CHAT_SYSTEM

REFUSAL_OUT_OF_SCOPE = (
    "I can only help with University of Sydney IT topics — things like UniKey, "
    "WiFi, VPN, email, Canvas, printing, software, and account access. "
    "Your question looks outside that scope, so I won't try to answer it."
)

REFUSAL_NO_RESULTS = (
    "I couldn't find anything relevant in the IT knowledge base for that question. "
    "If you believe this is an IT issue, please contact the Shared Service Centre: "
    "https://intranet.sydney.edu.au/employment/shared-service-centre.html"
)

# Back-compat alias (older imports / tests).
REFUSAL = REFUSAL_NO_RESULTS


class Citation(BaseModel):
    n: int
    title: str
    source_url: str
    source_type: str
    file: str
    chunk_index: int | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    latency_ms: int
    model: str


def _dedupe_docs(docs: list[Any]) -> list[Any]:
    """Collapse docs sharing the same metadata['file'], keeping highest-rank entry."""
    seen: set[str] = set()
    out: list[Any] = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        key = meta.get("file") or id(d)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def format_docs(docs: list[Any]) -> str:
    """Render retrieved docs as numbered context snippets."""
    limit = settings.chat_snippet_chars
    parts = []
    for i, d in enumerate(docs, start=1):
        meta = getattr(d, "metadata", {}) or {}
        title = meta.get("title") or meta.get("file") or f"doc {i}"
        source_type = meta.get("source_type", "unknown")
        url = meta.get("source_url", "")
        text = getattr(d, "page_content", "") or ""
        if limit and len(text) > limit:
            text = text[:limit].rstrip() + "…"
        parts.append(f"[{i}] {title} ({source_type})\n{url}\n{text}")
    return "\n\n".join(parts)


def _docs_to_citations(docs: list[Any]) -> list[Citation]:
    out: list[Citation] = []
    for i, d in enumerate(docs, start=1):
        meta = getattr(d, "metadata", {}) or {}
        out.append(
            Citation(
                n=i,
                title=meta.get("title") or meta.get("file") or f"doc {i}",
                source_url=meta.get("source_url", ""),
                source_type=meta.get("source_type", "unknown"),
                file=meta.get("file", ""),
                chunk_index=meta.get("chunk_index"),
            )
        )
    return out


def _build_llm():
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=settings.model_chat,
        base_url=settings.ollama_host,
        temperature=0.1,
        num_predict=settings.chat_num_predict,
        num_ctx=settings.chat_num_ctx,
    )


def _build_retriever():
    from uniassist.rag.retriever import get_ensemble_retriever

    return get_ensemble_retriever(k=settings.retrieval_k)


# Module-level singletons populated lazily so tests can monkeypatch the builders.
_retriever = None
_llm = None


def _retriever_invoke(question: str) -> list[Any]:
    global _retriever
    if _retriever is None:
        _retriever = _build_retriever()
    return _retriever.invoke(question)


def _llm_invoke(messages: list[Any]) -> Any:
    global _llm
    if _llm is None:
        _llm = _build_llm()
    return _llm.invoke(messages)


def _llm_stream(messages: list[Any]) -> Iterator[str]:
    global _llm
    if _llm is None:
        _llm = _build_llm()
    for chunk in _llm.stream(messages):
        text = getattr(chunk, "content", "") or ""
        if text:
            yield text


def answer(question: str) -> ChatResponse:
    """Single-shot RAG: retrieve, format context, chat, return cited answer."""
    from langchain_core.messages import HumanMessage, SystemMessage

    t0 = time.perf_counter()
    in_scope = is_in_scope(question)
    if not in_scope:
        return ChatResponse(
            answer=REFUSAL_OUT_OF_SCOPE,
            citations=[],
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=settings.model_chat,
        )

    docs = _dedupe_docs(_retriever_invoke(question))
    if not docs:
        return ChatResponse(
            answer=REFUSAL_NO_RESULTS,
            citations=[],
            latency_ms=int((time.perf_counter() - t0) * 1000),
            model=settings.model_chat,
        )

    context = format_docs(docs)
    messages = [
        SystemMessage(content=CHAT_SYSTEM),
        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {question}"),
    ]
    result = _llm_invoke(messages)
    text = getattr(result, "content", str(result))
    return ChatResponse(
        answer=text,
        citations=_docs_to_citations(docs),
        latency_ms=int((time.perf_counter() - t0) * 1000),
        model=settings.model_chat,
    )


def build_chat_chain():
    """Back-compat: expose `answer` for callers that wanted a chain object."""
    return answer


def answer_stream(question: str) -> Iterator[dict[str, Any]]:
    """Streaming RAG. Yields events:
    - {"type": "token", "text": str}
    - {"type": "final", "answer": str, "citations": list[dict],
       "latency_ms": int, "model": str}
    Refusal paths emit a single token event with the refusal text plus a final.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    t0 = time.perf_counter()

    def _final(text: str, citations: list[Citation]) -> dict[str, Any]:
        return {
            "type": "final",
            "answer": text,
            "citations": [c.model_dump() for c in citations],
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "model": settings.model_chat,
        }

    if not is_in_scope(question):
        yield {"type": "token", "text": REFUSAL_OUT_OF_SCOPE}
        yield _final(REFUSAL_OUT_OF_SCOPE, [])
        return

    docs = _dedupe_docs(_retriever_invoke(question))
    if not docs:
        yield {"type": "token", "text": REFUSAL_NO_RESULTS}
        yield _final(REFUSAL_NO_RESULTS, [])
        return

    citations = _docs_to_citations(docs)
    # Send citations early so the UI can show sources alongside streaming text.
    yield {"type": "citations", "citations": [c.model_dump() for c in citations]}

    context = format_docs(docs)
    messages = [
        SystemMessage(content=CHAT_SYSTEM),
        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {question}"),
    ]

    parts: list[str] = []
    for piece in _llm_stream(messages):
        parts.append(piece)
        yield {"type": "token", "text": piece}

    yield _final("".join(parts), citations)
