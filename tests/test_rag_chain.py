"""Tests for the RAG chain (mocked Ollama + retriever)."""
from __future__ import annotations

from langchain_core.documents import Document

from uniassist.rag import chain as rag_chain


def _doc(text: str, **meta) -> Document:
    return Document(page_content=text, metadata=meta)


def test_format_docs_numbers_and_urls():
    docs = [
        _doc(
            "Connect to UniWiFi step 1.",
            title="UniWiFi",
            source_type="web",
            source_url="https://example.com/wifi",
            file="wifi.md",
        ),
        _doc(
            "Reset your password here.",
            title="Password",
            source_type="servicenow_kb",
            source_url="https://service-now.com/kb",
            file="pw.md",
        ),
    ]
    out = rag_chain.format_docs(docs)
    assert "[1] UniWiFi (web)" in out
    assert "https://example.com/wifi" in out
    assert "[2] Password (servicenow_kb)" in out
    assert "https://service-now.com/kb" in out


def test_answer_extracts_citations_from_retrieved_docs(monkeypatch):
    docs = [
        _doc(
            "UniWiFi setup steps.",
            title="UniWiFi",
            source_type="web",
            source_url="https://example.com/wifi",
            file="wifi.md",
            chunk_index=0,
        ),
        _doc(
            "VPN GlobalProtect steps.",
            title="VPN",
            source_type="servicenow_kb",
            source_url="https://service-now.com/vpn",
            file="vpn.md",
            chunk_index=2,
        ),
    ]

    class FakeMsg:
        content = "Use UniWiFi [1]. For VPN, see [2]."

    monkeypatch.setattr(rag_chain, "_retriever_invoke", lambda q: docs)
    monkeypatch.setattr(rag_chain, "_llm_invoke", lambda m: FakeMsg())

    resp = rag_chain.answer("How do I connect to UniWiFi?")
    assert "[1]" in resp.answer
    assert len(resp.citations) == 2
    assert resp.citations[0].file == "wifi.md"
    assert resp.citations[0].source_url == "https://example.com/wifi"
    assert resp.citations[1].n == 2
    assert resp.citations[1].source_type == "servicenow_kb"
    assert resp.citations[1].chunk_index == 2
    assert resp.latency_ms >= 0
    assert resp.model


def test_answer_returns_out_of_scope_refusal(monkeypatch):
    def _fail_retr(_q):
        raise AssertionError("Retriever should not be called for out-of-scope")

    def _fail_llm(_m):
        raise AssertionError("LLM should not be called on refusal path")

    monkeypatch.setattr(rag_chain, "_retriever_invoke", _fail_retr)
    monkeypatch.setattr(rag_chain, "_llm_invoke", _fail_llm)

    resp = rag_chain.answer("recipe for apple pie")
    assert "scope" in resp.answer.lower()
    assert "Shared Service Centre" not in resp.answer
    assert resp.citations == []


def test_answer_returns_no_results_refusal_when_in_scope(monkeypatch):
    monkeypatch.setattr(rag_chain, "_retriever_invoke", lambda q: [])

    def _fail(_m):
        raise AssertionError("LLM should not be called on refusal path")

    monkeypatch.setattr(rag_chain, "_llm_invoke", _fail)

    resp = rag_chain.answer("How do I reset my UniKey password?")
    assert "Shared Service Centre" in resp.answer
    assert resp.citations == []


def test_dedupe_docs_collapses_same_file():
    docs = [
        _doc("full doc", title="WiFi", source_type="web",
             source_url="https://x/wifi", file="wifi.md"),
        _doc("chunk 2", title="WiFi", source_type="web",
             source_url="https://x/wifi", file="wifi.md", chunk_index=2),
        _doc("vpn", title="VPN", source_type="web",
             source_url="https://x/vpn", file="vpn.md", chunk_index=0),
    ]
    out = rag_chain._dedupe_docs(docs)
    assert len(out) == 2
    assert out[0].page_content == "full doc"
    assert out[1].metadata["file"] == "vpn.md"


def test_answer_dedupes_citations(monkeypatch):
    docs = [
        _doc("full", title="WiFi", source_type="web",
             source_url="https://x/wifi", file="wifi.md"),
        _doc("chunk", title="WiFi", source_type="web",
             source_url="https://x/wifi", file="wifi.md", chunk_index=2),
    ]

    class FakeMsg:
        content = "see [1]"

    monkeypatch.setattr(rag_chain, "_retriever_invoke", lambda q: docs)
    monkeypatch.setattr(rag_chain, "_llm_invoke", lambda m: FakeMsg())

    resp = rag_chain.answer("How do I connect to UniWiFi?")
    assert len(resp.citations) == 1
    assert resp.citations[0].n == 1
    assert resp.citations[0].file == "wifi.md"
