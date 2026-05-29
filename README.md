# UniAssist

> Local-first RAG + ticket-triage assistant for the University of Sydney ICT service desk.

Runs entirely offline against [Ollama](https://ollama.com) — no cloud, no Docker, no SSO required.
Sources: public University of Sydney student-IT pages + public ServiceNow KB articles.

## Status

Phase 1 (ingestion + indexing) under active development. See [plan.md](plan.md).

## Quickstart

```powershell
# 1. Install deps
uv sync

# 2. Copy env template
Copy-Item .env.example .env

# 3. Ingest corpus (scrape + clean + index)
uv run python -m uniassist.ingest.scraper
uv run python -m uniassist.ingest.clean
uv run python -m uniassist.ingest.build_index

# 4. Run API + UI (Phase 2+)
uv run uvicorn uniassist.api:app --reload
uv run streamlit run src/uniassist/ui/app.py
```

Or use the convenience runner:

```powershell
.\run.ps1 ingest
.\run.ps1 api
.\run.ps1 ui
.\run.ps1 eval
.\run.ps1 test
```

## Architecture

```
Web scraper (sydney.edu.au) ─┐
                             ├─► clean ─► chunk ─► embed (nomic-embed-text) ─► Chroma
Manual KB loader (data/raw_manual) ─┘

Chroma ─► retriever (MMR) ─► chat LLM (qwen2.5:7b-instruct) ─► answer + citations
                                                            └─► triage LLM ─► JSON
```

## License

MIT — see [LICENSE](LICENSE).
