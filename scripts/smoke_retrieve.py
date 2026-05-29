"""Quick retrieval smoke-test (BM25 + dense ensemble)."""
from uniassist.rag.retriever import get_ensemble_retriever

retriever = get_ensemble_retriever(k=3)

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
    for i, d in enumerate(retriever.invoke(q)):
        print(f"  [{i}] {d.metadata.get('title')}  ({d.metadata.get('source_type')})")
        print(f"       {d.metadata.get('source_url')}")
        snippet = d.page_content.strip().replace("\n", " ")
        print(f"       {snippet[:180]}")
