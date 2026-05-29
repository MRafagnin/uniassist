"""LCEL RAG chain: retrieve -> format -> chat -> cited answer."""
from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from uniassist.config import settings
from uniassist.guardrails import is_in_scope
from uniassist.rag.prompts import CHAT_SYSTEM

REFUSAL = (
    "I don't have information about that in the knowledge base. Please contact the "
    "Shared Service Centre: "
    "https://intranet.sydney.edu.au/employment/shared-service-centre.html"
)


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


def format_docs(docs: list[Any]) -> str:
    """Render retrieved docs as numbered context snippets."""
    parts = []
    for i, d in enumerate(docs, start=1):
        meta = getattr(d, "metadata", {}) or {}
        title = meta.get("title") or meta.get("file") or f"doc {i}"
        source_type = meta.get("source_type", "unknown")
        url = meta.get("source_url", "")
        text = getattr(d, "page_content", "")
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


def answer(question: str) -> ChatResponse:
    """Single-shot RAG: retrieve, format context, chat, return cited answer."""
    from langchain_core.messages import HumanMessage, SystemMessage

    t0 = time.perf_counter()
    docs = _retriever_invoke(question)

    if not docs or not is_in_scope(question):
        return ChatResponse(
            answer=REFUSAL,
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
