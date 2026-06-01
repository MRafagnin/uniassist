# UniAssist

> Local-first RAG + ticket-triage assistant for the University of Sydney ICT service desk.

Runs entirely offline against [Ollama](https://ollama.com) — no cloud, no Docker, no SSO required.
Sources: public University of Sydney student-IT pages + public ServiceNow KB articles + an optional manual KB drop folder.

## Status

| Phase | Scope | State |
| --- | --- | --- |
| 1 | Ingestion (scrape + clean + index) | Complete |
| 2 | FastAPI + RAG chain + triage + SQLite logging + guardrails | Complete |
| 3 | Streamlit UI (Chat / Triage / Metrics) + citation dedupe + `/recent` | Complete |

Project complete. The eval harness, screenshots, Loom video, and cover-letter pitch from the original Phase 4 roadmap are not included.

See [implementations/plan.md](implementations/plan.md) for the full roadmap and [implementations/completed/](implementations/completed/) for per-phase write-ups.

## Quickstart

```powershell
# 1. Install deps
uv sync

# 2. Copy env template and pull models
Copy-Item .env.example .env
ollama pull qwen2.5:7b-instruct
ollama pull nomic-embed-text
ollama pull llama3.1:8b   # eval judge only

# 3. Ingest corpus (scrape + render ServiceNow KB + clean + index)
.\run.ps1 ingest

# 4. Run API and UI in two terminals
.\run.ps1 api
.\run.ps1 ui
```

`run.ps1` tasks: `ingest | api | ui | eval | test`. The UI talks to the API over HTTP at `http://localhost:8000` (override with `UNIASSIST_API`).

## Architecture

```
Web scraper (sydney.edu.au) ──┐
ServiceNow KB renderer ───────┼─► clean ─► chunk ─► embed (nomic-embed-text) ─► Chroma
Manual KB loader (data/raw_manual) ─┘

                  ┌─► RAG chain ─► chat LLM (qwen2.5:7b-instruct) ─► answer + citations
Chroma ─► retriever (ensemble: dense + BM25, dedup by file)
                  └─► Triage chain ─► structured JSON (category / priority / queue)

FastAPI: /chat  /triage  /metrics  /recent  /healthz   ──►  SQLite (PII-redacted)
   ▲
   │ httpx (timeout 180s)
   │
Streamlit UI: Chat | Triage | Metrics
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/chat` | RAG answer with numbered citations |
| POST | `/triage` | Structured ticket classification |
| GET | `/metrics` | Per-endpoint counts + P50/P95 latency + top categories |
| GET | `/recent?limit=20` | Recent calls (PII-redacted) for the Metrics tab |
| GET | `/healthz` | Liveness + model + doc count |

## UI

- **Chat** — chat history in `st.session_state`, numbered `[n]` citations with a coloured chip per source type (`Web` / `ServiceNow KB` / `Manual`), per-turn latency caption, **Sources** expander. Chat input is pinned to the bottom of the viewport and recenters when the sidebar is toggled.
- **Triage** — text area → structured JSON with confidence bar, rationale, raw-JSON expander.
- **Metrics** — totals + per-endpoint latency bar chart + top categories + recent-queries dataframe (confirms PII redaction visually).

## Tests

```powershell
uv run pytest -q
uv run ruff check .
```

## License

MIT — see [LICENSE](LICENSE).
