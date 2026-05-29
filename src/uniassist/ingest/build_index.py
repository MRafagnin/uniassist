"""Chunk processed markdown -> embed via Ollama -> persist to Chroma.

Reads everything in ``data/processed/``; metadata on each chunk includes
``source_url``, ``title``, ``source_type``, and ``chunk_index``.
"""
from __future__ import annotations

import contextlib
import logging
import re
from pathlib import Path

from uniassist.config import settings

log = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _parse_doc(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {"source_url": path.as_uri(), "title": path.stem, "source_type": "unknown"}, text
    meta_block, body = m.group(1), m.group(2)
    meta: dict[str, str] = {}
    for line in meta_block.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body.strip()


def build_index(processed_dir: Path | None = None, chroma_dir: Path | None = None) -> int:
    # Imports are local so that ``import build_index`` is cheap and the module
    # is importable in tests without LangChain installed at collection time.
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_chroma import Chroma
    from langchain_core.documents import Document
    from langchain_ollama import OllamaEmbeddings

    processed_dir = processed_dir or settings.processed_dir
    chroma_dir = chroma_dir or settings.chroma_dir
    chroma_dir.mkdir(parents=True, exist_ok=True)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )

    docs: list[Document] = []
    for path in sorted(processed_dir.glob("*.md")):
        meta, body = _parse_doc(path)
        if len(body) < 50:
            continue
        chunks = splitter.split_text(body)
        for i, chunk in enumerate(chunks):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source_url": meta.get("source_url", ""),
                        "title": meta.get("title", path.stem),
                        "source_type": meta.get("source_type", "unknown"),
                        "chunk_index": i,
                        "file": path.name,
                    },
                )
            )
    if not docs:
        log.warning("No chunks produced — is %s empty?", processed_dir)
        return 0

    embeddings = OllamaEmbeddings(model=settings.model_embed, base_url=settings.ollama_host)
    store = Chroma(
        collection_name="uniassist",
        embedding_function=embeddings,
        persist_directory=str(chroma_dir),
    )
    # Replace prior collection contents.
    with contextlib.suppress(Exception):
        store.delete_collection()
    store = Chroma(
        collection_name="uniassist",
        embedding_function=embeddings,
        persist_directory=str(chroma_dir),
    )
    store.add_documents(docs)
    log.info("Indexed %d chunks from %d docs -> %s", len(docs), len({d.metadata['file'] for d in docs}), chroma_dir)
    return len(docs)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_index()
