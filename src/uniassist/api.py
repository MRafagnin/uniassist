"""FastAPI app exposing /chat, /triage, /metrics, /healthz."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from uniassist import logging_store
from uniassist.config import settings
from uniassist.guardrails import redact
from uniassist.rag.chain import ChatResponse
from uniassist.rag.chain import answer as rag_answer
from uniassist.rag.chain import answer_stream as rag_answer_stream
from uniassist.triage.chain import TriageResponse
from uniassist.triage.chain import triage as triage_call

_health_cache: dict[str, Any] = {
    "model_chat": settings.model_chat,
    "ollama_host": settings.ollama_host,
    "chroma_docs": 0,
    "ollama_available": False,
}


def _refresh_health_cache() -> None:
    try:
        r = httpx.get(f"{settings.ollama_host}/api/tags", timeout=2.0)
        _health_cache["ollama_available"] = r.status_code == 200
    except Exception:
        _health_cache["ollama_available"] = False
    try:
        from langchain_chroma import Chroma
        from langchain_ollama import OllamaEmbeddings

        emb = OllamaEmbeddings(model=settings.model_embed, base_url=settings.ollama_host)
        store = Chroma(
            collection_name="uniassist",
            embedding_function=emb,
            persist_directory=str(settings.chroma_dir),
        )
        _health_cache["chroma_docs"] = store._collection.count()
    except Exception:
        _health_cache["chroma_docs"] = 0


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging_store.init_db()
    _refresh_health_cache()
    yield


app = FastAPI(title="UniAssist", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)


class TriageRequest(BaseModel):
    ticket_text: str = Field(..., min_length=1)


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"status": "ok", **_health_cache}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    resp = rag_answer(req.question)
    logging_store.log_query(
        endpoint="chat",
        input_redacted=redact(req.question),
        retrieved_ids=[c.file for c in resp.citations],
        answer=resp.answer,
        latency_ms=resp.latency_ms,
        model=resp.model,
    )
    return resp


@app.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """NDJSON stream of {token|citations|final} events."""
    def _gen():
        final_evt: dict[str, Any] | None = None
        try:
            for evt in rag_answer_stream(req.question):
                if evt.get("type") == "final":
                    final_evt = evt
                yield json.dumps(evt, ensure_ascii=False) + "\n"
        except Exception as exc:  # noqa: BLE001
            yield json.dumps({"type": "error", "message": str(exc)}) + "\n"
            return
        if final_evt is not None:
            logging_store.log_query(
                endpoint="chat",
                input_redacted=redact(req.question),
                retrieved_ids=[c.get("file", "") for c in final_evt.get("citations", [])],
                answer=final_evt.get("answer", ""),
                latency_ms=final_evt.get("latency_ms", 0),
                model=final_evt.get("model", settings.model_chat),
            )

    return StreamingResponse(_gen(), media_type="application/x-ndjson")


@app.post("/triage", response_model=TriageResponse)
def triage_endpoint(req: TriageRequest) -> TriageResponse:
    resp = triage_call(req.ticket_text)
    logging_store.log_query(
        endpoint="triage",
        input_redacted=redact(req.ticket_text),
        answer=json.dumps(resp.result.model_dump()),
        latency_ms=resp.latency_ms,
        model=resp.model,
    )
    return resp


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    return logging_store.summary()


@app.get("/recent")
def recent(limit: int = Query(20, ge=1, le=200)) -> list[dict[str, Any]]:
    return logging_store.recent(n=limit)
