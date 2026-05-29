"""Retriever factory (Phase 2).

Two flavours are exposed:

* :func:`get_retriever` — dense-only MMR retriever over the Chroma store.
* :func:`get_ensemble_retriever` — BM25 (sparse) + dense ensemble.

For our title-dense concierge stubs, BM25 carries most of the brand-name
discrimination (e.g. distinguishing "What is Zoom?" from "What is Qualtrics?"),
while dense embeddings handle paraphrased intent.
"""
from __future__ import annotations

from pathlib import Path

from uniassist.config import settings


def get_retriever(k: int | None = None, fetch_k: int | None = None):
    from langchain_chroma import Chroma
    from langchain_ollama import OllamaEmbeddings

    embeddings = OllamaEmbeddings(model=settings.model_embed, base_url=settings.ollama_host)
    store = Chroma(
        collection_name="uniassist",
        embedding_function=embeddings,
        persist_directory=str(settings.chroma_dir),
    )
    return store.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": k or settings.retrieval_k,
            "fetch_k": fetch_k or settings.retrieval_fetch_k,
        },
    )


def get_ensemble_retriever(
    k: int | None = None,
    bm25_weight: float = 0.6,
    processed_dir: Path | None = None,
):
    import re as _re

    from langchain.retrievers import EnsembleRetriever
    from langchain_chroma import Chroma
    from langchain_community.retrievers import BM25Retriever
    from langchain_core.documents import Document
    from langchain_ollama import OllamaEmbeddings

    from uniassist.ingest.build_index import _parse_doc

    processed_dir = processed_dir or settings.processed_dir
    k = k or settings.retrieval_k

    # Strip common interrogative / function words so brand names (e.g. "Zoom",
    # "Adobe") dominate the BM25 score instead of "what / how / is / do / I".
    _STOP = {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
        "for", "from", "how", "i", "in", "is", "it", "my", "of", "on", "or",
        "so", "the", "this", "to", "what", "when", "where", "which", "who",
        "why", "with", "you", "your",
    }
    _TOKEN_RE = _re.compile(r"[A-Za-z0-9]+")

    def _preprocess(text: str) -> list[str]:
        return [
            t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOP
        ]

    embeddings = OllamaEmbeddings(model=settings.model_embed, base_url=settings.ollama_host)
    store = Chroma(
        collection_name="uniassist",
        embedding_function=embeddings,
        persist_directory=str(settings.chroma_dir),
    )
    dense = store.as_retriever(search_kwargs={"k": k})

    corpus: list[Document] = []
    for path in sorted(processed_dir.glob("*.md")):
        meta, body = _parse_doc(path)
        if len(body) < 50:
            continue
        corpus.append(
            Document(
                page_content=body,
                metadata={
                    "source_url": meta.get("source_url", ""),
                    "title": meta.get("title", path.stem),
                    "source_type": meta.get("source_type", "unknown"),
                    "file": path.name,
                },
            )
        )
    bm25 = BM25Retriever.from_documents(corpus, preprocess_func=_preprocess)
    bm25.k = k

    return EnsembleRetriever(
        retrievers=[bm25, dense],
        weights=[bm25_weight, 1.0 - bm25_weight],
    )
