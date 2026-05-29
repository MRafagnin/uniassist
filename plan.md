# Plan: UniAssist — AI ICT Service Desk Copilot

A 2–3 day, fully-local prototype targeting the **Innovation Developer** role at a university ICT team. RAG-based assistant over the University of Sydney student IT help pages + ServiceNow KB articles, plus a structured ticket-triage endpoint.

**Stack:** Ollama (`qwen2.5:7b-instruct` + `nomic-embed-text` + `llama3.1:8b` judge), LangChain, Chroma, FastAPI, Streamlit. **No cloud deploy, no Docker** — Loom video demo.

---

## Decisions (locked)

- **Corpus** (two sources, unified pipeline):
  1. **Scraped** — `https://www.sydney.edu.au/students/student-it.html` and child help pages (public, no auth).
  2. **Manual KB drop** — ServiceNow KB articles under topic `4d7d2ae687d31dd0fb4dab0a0cbb3542`, saved manually by the user (browser "Save as HTML Only") into `data/raw_manual/`. ServiceNow is SSO-gated and cannot be crawled headlessly.
  3. **Fallback** — ~20 hand-written markdown FAQs if either source is thin.
- **Chat / triage model:** Ollama `qwen2.5:7b-instruct` (strong structured-JSON output).
- **Embedding model:** Ollama `nomic-embed-text` (768-dim, fast).
- **Eval judge model:** Ollama `llama3.1:8b` (separate from generator → less self-bias).
- **Triage taxonomy:** grounded in actual corpus categories (keeps eval honest).
- **Deploy:** fully local, no Docker. Deliverable is a **public** GitHub repo (public from day 1, small commits) + Loom walkthrough + README case study.
- **Frontend:** Streamlit, three tabs — `Chat`, `Triage`, `Metrics`.

## Scope

**In:** scraper, manual-KB loader, ingestion + vector store, RAG chat API, triage API, 3-tab Streamlit UI, eval harness (~25 Q&A), SQLite query log, metrics dashboard, README case study, Loom video.

**Out:** auth/SSO, ServiceNow API integration, live ticket-system integration, fine-tuning, multi-tenant, cloud hosting, Docker (machine cannot run it), streaming UI (only if time allows).

---

## Repository layout

```
uniassist/
├── README.md                 # case-study: problem → arch → results → roadmap
├── pyproject.toml            # uv
├── .env.example              # OLLAMA_HOST, MODEL_CHAT, MODEL_EMBED, MODEL_JUDGE, CORPUS_DIR
├── run.ps1                   # Windows convenience: ingest / api / ui / eval / test
├── data/
│   ├── raw/                  # scraped HTML (gitignored)
│   ├── raw_manual/           # user-dropped ServiceNow KB exports (.html or .md)
│   ├── processed/            # cleaned markdown chunks
│   └── chroma/               # persisted vector store (gitignored)
├── src/uniassist/
│   ├── __init__.py
│   ├── config.py             # pydantic-settings, env-driven
│   ├── ingest/
│   │   ├── scraper.py        # httpx + selectolax, polite crawl, robots.txt
│   │   ├── manual_loader.py  # walk data/raw_manual/, parse .html/.md, normalise
│   │   ├── clean.py          # html → markdown, strip nav/footer
│   │   └── build_index.py    # chunk → embed → Chroma (handles both sources)
│   ├── rag/
│   │   ├── retriever.py      # Chroma + MMR
│   │   ├── prompts.py        # CHAT_SYSTEM, TRIAGE_SYSTEM
│   │   └── chain.py          # LangChain LCEL: retrieve → format → llm → cite
│   ├── triage/
│   │   ├── schema.py         # Pydantic: Category, Priority, SuggestedQueue
│   │   └── chain.py          # structured-output chain
│   ├── guardrails.py         # out-of-scope refusal, PII redaction (email/SID regex)
│   ├── logging_store.py      # SQLite: queries, retrieved_ids, latency_ms, tokens
│   ├── api.py                # FastAPI: /chat, /triage, /metrics, /healthz
│   └── ui/
│       └── app.py            # Streamlit: Chat | Triage | Metrics tabs
├── eval/
│   ├── qa_pairs.yaml         # ~25 Q + expected_source_url + ideal_answer + must_contain
│   ├── run_eval.py           # retrieval@k, faithfulness (llama3.1:8b judge)
│   └── results/              # markdown report committed per run
└── tests/
    ├── test_clean.py
    ├── test_manual_loader.py
    ├── test_chunking.py
    ├── test_triage_schema.py
    └── test_guardrails.py
```

---

## Phased steps

### Phase 1 — Foundations (Day 1)

1. **Project scaffold:** `uv init`, pin Python 3.11, install `langchain`, `langchain-ollama`, `langchain-chroma`, `chromadb`, `fastapi`, `uvicorn`, `streamlit`, `httpx`, `selectolax`, `markdownify`, `pydantic-settings`, `pytest`, `ruff`. Git init, `.gitignore`, `.env.example`.
2. **Scraper** (`ingest/scraper.py`): BFS from `sydney.edu.au/students/student-it.html`, 1–2 levels deep, same-domain only, respect `robots.txt`, 1 req/sec, cap ~150 pages. Save raw HTML + URL manifest to `data/raw/`.
3. **Cleaner** (`ingest/clean.py`): strip nav/footer/scripts, convert to markdown, drop pages <200 chars. Output `data/processed/<slug>.md` with frontmatter `{source_url, title, source_type, scraped_at}`.
4. **Manual KB loader** (`ingest/manual_loader.py`): walk `data/raw_manual/`, accept `.html` (parse with selectolax, strip ServiceNow chrome) or `.md` (passthrough), extract `source_url` from `<link rel=canonical>` or frontmatter, normalise into `data/processed/` with `source_type: servicenow_kb`.
5. **Index builder** (`ingest/build_index.py`): `RecursiveCharacterTextSplitter` (chunk 800, overlap 120), embed with `OllamaEmbeddings(model="nomic-embed-text")`, persist to Chroma at `data/chroma/`. Stores `source_type` in chunk metadata so the UI can badge `Web` vs `ServiceNow KB`.
6. **Smoke test:** load retriever in a notebook, run 5 questions, eyeball results. Tune chunk size if retrieval is weak.

### Phase 2 — Core product (Day 2)

7. **RAG chain** (`rag/chain.py`): LCEL — `{question} → retriever (MMR, k=5) → format_docs (numbered with source URLs) → ChatOllama(qwen2.5:7b-instruct) → parser`. System prompt enforces: cite sources as `[1]`, refuse if no relevant context, never invent URLs.
8. **Triage chain** (`triage/chain.py`): Pydantic `TriageResult{category: Literal[...], subcategory: str, priority: Literal["P1"-"P4"], suggested_queue: str, rationale: str, confidence: float}`. Use `ChatOllama(format="json")` + Pydantic validation + retry-on-parse-fail. Categories: `WiFi`, `Email/M365`, `VPN`, `Account/Password`, `LMS/Canvas`, `Hardware`, `Software-licensing`, `Other`.
9. **FastAPI** (`api.py`): `POST /chat`, `POST /triage`, `GET /metrics`, `GET /healthz`. Every call writes to `logging_store`.
10. **Guardrails + PII** (`guardrails.py`): regex-redact emails and 9-digit student IDs before logging; out-of-scope refusal (keyword heuristic or cheap LLM call).

### Phase 3 — UX + observability (Day 2 evening → Day 3 morning)

11. **Streamlit UI** (`ui/app.py`):
    - **Chat tab** — chat history, answer + numbered citations as clickable links, latency badge, source-type chip (Web / ServiceNow).
    - **Triage tab** — textarea + "Triage" button → renders JSON + confidence bar + rationale.
    - **Metrics tab** — SQLite-backed: questions/day, avg latency, P50/P95, est. tokens, top categories. `st.metric` + `st.bar_chart`.
12. **SQLite logging** (`logging_store.py`): table `queries(id, ts, endpoint, input_redacted, retrieved_ids, answer, latency_ms, tokens_in, tokens_out, model)`.

### Phase 4 — Evaluation + narrative (Day 3)

13. **Eval set** (`eval/qa_pairs.yaml`): 25 hand-written Q&A pairs (drafted during prep). Schema: `{question, expected_source_url, ideal_answer, must_contain: [...]}`.
14. **Eval runner** (`eval/run_eval.py`): metrics — `retrieval@5`, `faithfulness` (LLM-as-judge via `llama3.1:8b`), `must_contain_hits`, avg latency. Emit `eval/results/YYYY-MM-DD.md` table.
15. **README case study:** problem → Mermaid arch diagram → screenshots → eval results table → explicit note that ServiceNow KB is SSO-gated and was ingested via the manual loader → limitations → roadmap (SSO/SAML to ServiceNow KB API, ServiceNow incident webhook for live triage, feedback loop, fine-tune small classifier).
16. **Tests** (`tests/`): cleaner removes nav, manual loader parses a sample ServiceNow HTML export, chunker handles short docs, triage schema rejects invalid priority, guardrail redacts a sample email.
17. **Windows runner** (`run.ps1`): tasks `ingest | api | ui | eval | test` wrapping `uv run`.
18. **Loom video** (90 sec): problem → live chat demo with a citation pointing to ServiceNow + one to web → triage demo → metrics tab → eval results table. Link in cover letter + repo README top.

---

## Verification

1. `uv run pytest -q` → all green.
2. `uv run ruff check .` → clean.
3. `python -m uniassist.ingest.build_index` → completes, prints chunk count, Chroma dir non-empty.
4. `uvicorn uniassist.api:app` + `curl -X POST localhost:8000/chat -d '{"question":"How do I connect to UniWiFi?"}'` → answer with at least one `[n]` citation to a real `sydney.edu.au` URL.
5. `curl -X POST localhost:8000/triage -d '{"ticket_text":"My VPN keeps dropping every 10 minutes"}'` → valid JSON, `category=VPN`, priority in `P1..P4`.
6. `streamlit run src/uniassist/ui/app.py` → all 3 tabs render; Metrics populates after a few queries.
7. `python eval/run_eval.py` → results markdown with **retrieval@5 ≥ 0.7** (tune chunking if not).
8. Manual: out-of-scope question ("what's the weather?") → polite refusal, no fabricated citation.
9. Manual: ticket containing a fake email → SQLite row shows it redacted.

---

## Risks & mitigations

- **Scraping yields low-quality text** → manual KB drop covers the gap; final fallback is ~20 hand-written FAQs.
- **ServiceNow HTML export varies by browser** → manual loader is permissive (CSS selectors with fallbacks); on parse failure log + skip rather than abort.
- **`qwen2.5:7b` too slow on CPU** → drop to `qwen2.5:3b-instruct`; note tradeoff in README.
- **`format="json"` flaky** → retry-with-repair prompt; Pydantic validation catches malformed output.
- **Time slip** → cut Metrics tab first, then `run.ps1`, then eval automation (keep manual eval table). Chat + Triage + README + Loom are non-negotiable.

---

## Application-package deliverables

- Public GitHub repo with clean commit history.
- README as case study (problem → arch diagram → results → roadmap).
- `eval/results/*.md` showing measured retrieval@5 and faithfulness.
- 90-sec Loom walkthrough.
- One-paragraph cover-letter pitch linking repo + Loom.

---

## Reference

- Prerequisites checklist: [prerequisites.md](prerequisites.md)
- Role description: [role.md](role.md)
