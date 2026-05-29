"""Quick retrieval smoke-test."""
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

from uniassist.config import settings

emb = OllamaEmbeddings(model=settings.model_embed, base_url=settings.ollama_host)
store = Chroma(
    collection_name="uniassist",
    embedding_function=emb,
    persist_directory=str(settings.chroma_dir),
)

QUERIES = [
    "software for managing bibliographies and references",
    "how do I set up multi factor authentication",
    "connect to the university VPN",
    "what is Zoom and how do I sign in",
    "Adobe Creative Cloud access",
    "I cannot access my Canvas course",
]

for q in QUERIES:
    print(f"\n=== Q: {q}")
    for i, d in enumerate(store.similarity_search(q, k=3)):
        print(f"  [{i}] {d.metadata.get('title')}  ({d.metadata.get('source_type')})")
        print(f"       {d.metadata.get('source_url')}")
        snippet = d.page_content.strip().replace("\n", " ")
        print(f"       {snippet[:180]}")
