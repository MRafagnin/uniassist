"""Retriever factory (Phase 2)."""
from __future__ import annotations

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
