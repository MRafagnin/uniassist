# Phase 2 — RAG chain, Triage chain, FastAPI

**Branch:** `phase-2-rag-triage-api`

Fill in the six stub modules that already exist (`rag/chain.py`, `triage/chain.py`, `api.py`, `logging_store.py`, `guardrails.py`, `rag/prompts.py`) to deliver a working `POST /chat` (cited RAG), `POST /triage` (structured JSON), `GET /metrics`, `GET /healthz`, all backed by SQLite. LCEL throughout. No UI — that's Phase 3.

**Decisions (approved):**
- Single-shot `/chat` (no server-side conversation memory). Phase 3 Streamlit stitches turns client-side.
- Helpful refusal that points to the Shared Service Centre article when the question is out of scope or retrieval is empty.
- No streaming for Phase 2.

---

## Sub-phases

### 2A — RAG chain (`src/uniassist/rag/chain.py`)

LCEL: question → `get_ensemble_retriever(k=settings.retrieval_k)` → `format_docs` (numbered `[n] title (source_type)\nURL\n<chunk text>`) → `ChatPromptTemplate(CHAT_SYSTEM)` → `ChatOllama(model=settings.model_chat, base_url=settings.ollama_host, temperature=0.1)` → `StrOutputParser`.

Public entry: `answer(question: str) -> ChatResponse` returning `{answer, citations, latency_ms, model}` where `Citation = {n, title, source_url, source_type, file, chunk_index}`. Run retriever once, derive citations from the same docs. Empty-context branch returns canned helpful refusal pointing to the Shared Service Centre KB article.

### 2B — Triage chain (`src/uniassist/triage/chain.py`)

LCEL: `ChatPromptTemplate(TRIAGE_SYSTEM)` → `ChatOllama(model=settings.model_chat, format="json", temperature=0)` → `StrOutputParser` → `json.loads` → `TriageResult.model_validate`. Wrap with `tenacity.retry(stop=stop_after_attempt(2))`. On final failure return `TriageResult(category="Other", priority="P3", confidence=0.0, rationale="parse_failed: …")`.

Public entry: `triage(ticket_text: str) -> TriageResponse{result, latency_ms, model, retries}`.

Verify `triage/schema.py` has `subcategory` and `suggested_queue` — add if missing.

### 2C — SQLite log (`src/uniassist/logging_store.py`)

Finalise schema:
```
queries(id INTEGER PK, ts TEXT, endpoint TEXT, input_redacted TEXT,
        retrieved_ids TEXT JSON, answer TEXT, latency_ms INTEGER,
        tokens_in INTEGER NULL, tokens_out INTEGER NULL, model TEXT)
```
Stdlib `sqlite3` with `check_same_thread=False`, one shared connection guarded by a `threading.Lock`. Helpers: `init_db()` (idempotent CREATE), `log_query(...)`, `recent(n=50)`, `summary()` (counts by endpoint, P50/P95 latency via SQL, top categories from triage answer JSON).

### 2D — Guardrails (`src/uniassist/guardrails.py`)

Verify existing `redact(text)` (email + 9-digit SID regex → `[EMAIL]` / `[SID]`); keep as-is. Add `is_in_scope(question: str) -> bool` — keyword heuristic (wifi/vpn/email/outlook/zoom/adobe/mfa/okta/canvas/unikey/password/sso/servicenow/laptop/mac/windows/library/print/software/license + IT verbs install/connect/configure/log in/sign in/access/set up/reset/update). Soft signal only; `/chat` short-circuits to a helpful refusal when `is_in_scope=False` AND retriever returns zero relevant docs.

### 2E — FastAPI (`src/uniassist/api.py`)

Endpoints:
- `GET /healthz` → `{status, model_chat, ollama_host, chroma_docs}`. Cache Ollama `/api/tags` + Chroma count from startup.
- `POST /chat` body `{question}` → `ChatResponse`. Calls `rag.chain.answer`, then `log_query(endpoint="chat", input_redacted=redact(question), retrieved_ids=[c.file for c in citations], answer=answer, ...)`.
- `POST /triage` body `{ticket_text}` → `TriageResponse`. Calls `triage.chain.triage`, then `log_query(endpoint="triage", input_redacted=redact(ticket_text), answer=json.dumps(result.model_dump()), ...)`.
- `GET /metrics` → `logging_store.summary()`.

Pydantic request/response models live in `api.py` only (chains stay framework-agnostic). Lifespan handler calls `init_db()` and warms one embedding pass. CORS allow `http://localhost:8501` (Streamlit dev).

### 2F — Tests + verification

New unit tests (mock Ollama, no live model calls):
- `tests/test_rag_chain.py` — `format_docs` numbering + URL formatting; `answer()` with monkeypatched retriever + LLM → assert citation extraction matches retrieved docs.
- `tests/test_triage_chain.py` — monkeypatch LLM: valid JSON → `TriageResult`; invalid JSON twice → fallback `Other`.
- `tests/test_logging_store.py` — temp DB; `init_db` + `log_query` + `summary` round-trip; P50/P95 calculation on synthetic latencies.
- `tests/test_api.py` — `fastapi.testclient.TestClient`, monkeypatched chains; assert request/response shapes + DB row written; CORS header present.
- Extend `tests/test_guardrails.py` for `is_in_scope` true/false cases.

---

## Execution order

1. **2C SQLite** *parallel with* **2D Guardrails** — no deps.
2. **2A RAG chain** *parallel with* **2B Triage chain** — both depend on prompts + their own module fundamentals.
3. **2E FastAPI** — depends on 2A/2B/2C/2D.
4. Tests written alongside each module; manual `curl` smoke at the end.
5. Commits: `feat(log+guard): …`, `feat(rag): …`, `feat(triage): …`, `feat(api): …`. PR `phase-2-rag-triage-api` → `main` at the end.

---

## Relevant files

- [src/uniassist/rag/chain.py](../src/uniassist/rag/chain.py) — replace `build_chat_chain` stub with LCEL + `answer()`.
- [src/uniassist/rag/prompts.py](../src/uniassist/rag/prompts.py) — verify CHAT_SYSTEM enforces `[n]` citation, no-URL-invention, prefer ServiceNow body over web snippet; TRIAGE_SYSTEM enforces JSON-only with embedded schema + priority heuristics.
- [src/uniassist/rag/retriever.py](../src/uniassist/rag/retriever.py) — reuse `get_ensemble_retriever` as-is.
- [src/uniassist/triage/schema.py](../src/uniassist/triage/schema.py) — confirm fields; add `subcategory` / `suggested_queue` if missing.
- [src/uniassist/triage/chain.py](../src/uniassist/triage/chain.py) — replace stub.
- [src/uniassist/logging_store.py](../src/uniassist/logging_store.py) — finalise schema + helpers.
- [src/uniassist/guardrails.py](../src/uniassist/guardrails.py) — verify `redact`; add `is_in_scope`.
- [src/uniassist/api.py](../src/uniassist/api.py) — replace `/healthz`-only stub with all four endpoints + lifespan + CORS.
- New: [tests/test_rag_chain.py](../tests/test_rag_chain.py), [tests/test_triage_chain.py](../tests/test_triage_chain.py), [tests/test_logging_store.py](../tests/test_logging_store.py), [tests/test_api.py](../tests/test_api.py).

---

## Decisions

- **Tokens NULL for v1.** Ollama exposes usage only via direct invoke; threading through LCEL is messy and not worth it. Documented in README.
- **Single retriever invocation per chat call** — chain accepts pre-fetched docs so citations + context come from the same list.
- **`format="json"` + Pydantic + 1 retry** rather than `with_structured_output` (flaky with ChatOllama JSON mode for our pydantic version).
- **`is_in_scope` is a soft signal**, not a hard gate.
- **Single-shot `/chat`** (no server-side memory).
- **Helpful refusal** pointing to the Shared Service Centre article on empty context.
- **No streaming.**

**Out of scope for Phase 2:** Streamlit UI, eval harness, README rewrite, per-call token accounting, streaming, multi-turn memory.

---

## Verification

Result: **all 8 scenarios passed** against a live Ollama (`qwen2.5:7b-instruct` chat, `nomic-embed-text` embed) on CPU.

1. `uv run ruff check .` → `All checks passed!`
2. `uv run pytest -q` → 37 passed (25 existing + 12 new).
3. `GET /healthz` → `{"status":"ok","model_chat":"qwen2.5:7b-instruct","ollama_host":"http://localhost:11434","chroma_docs":1251,"ollama_available":true}`.
4. `POST /chat` "How do I connect to UniWiFi?" → 10-step answer citing `[1,6]` against real `sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=…` URLs; latency ~84s on CPU (above the 30s target — noted as a Phase 3 perf item, see below).
5. `POST /triage` "My VPN drops every 10 min" → `category="VPN"`, `priority="P3"`, `suggested_queue="ICT-Network"`, `confidence=0.85`, `retries=0`, latency ~17s.
6. `POST /chat` "What's the weather like today?" → canned refusal pointing to `https://intranet.sydney.edu.au/employment/shared-service-centre.html`, `citations=[]` (short-circuit via `is_in_scope=False`, no LLM call — ~9s wall clock is the retriever warm-up + BM25 corpus load).
7. `POST /chat` containing `student@uni.edu.au` → SQLite row 2 has `input_redacted = "Can you help me email [REDACTED_EMAIL] about wifi?"`.
8. `GET /metrics` → `{"counts":{"chat":2,"triage":1},"latency_ms":{…P50/P95…},"top_categories":[["VPN",1]]}`.

### Deviations from the plan

- **CHAT_SYSTEM does not embed the exact refusal string.** The first iteration told the LLM to reply with the literal Shared Service Centre sentence verbatim; `qwen2.5:7b-instruct` then parroted it even when 10 highly-relevant ServiceNow KBs were retrieved. Final prompt asks the model to answer from context and only mention lack of info briefly if nothing applies; the canned Shared Service Centre refusal is emitted **server-side** in `rag.chain.answer` before the LLM is called.
- **Refusal trigger is `not docs OR not is_in_scope(question)`**, not the planned `AND`. The BM25 half of the ensemble retriever always returns *something* for any non-empty query, so the `AND` gate never fired for out-of-scope questions like "What's the weather?". Treating `is_in_scope=False` as a hard short-circuit is cheap (no LLM call) and matches the spec's intent.
- **`tenacity` not used.** Triage retry is a plain 2-attempt loop over `(json.JSONDecodeError, ValidationError, ValueError)` — simpler, no dependency surface, identical behaviour for our 2-try budget.
- **`logging_store.reset_for_tests(path)`** added for test isolation (the shared `threading.Lock`-guarded connection persists across `TestClient` instances in the same pytest process).
- **`/healthz` payload** also includes `ollama_available` (httpx ping of `/api/tags`) on top of the four planned fields.
- **`guardrails.is_likely_in_scope`** kept as a back-compat alias delegating to the new `is_in_scope`, so Phase 1 tests continue to pass unchanged.

### Known issues to carry forward

- **/chat latency ~70–150s on CPU**, well above the 30s target in the plan. Driven by the 70B-token context (k=5 ensemble × ~1KB each + system prompt) plus CPU inference. Mitigations to consider in Phase 3: trim ensemble to k=3, drop the dense half from the retriever for short queries, or switch to a smaller chat model for the demo.
- **Chroma telemetry warnings** on stdout (`Failed to send telemetry event …: capture() takes 1 positional argument but 3 were given`) — harmless upstream Chroma 0.5/posthog mismatch. Set `ANONYMIZED_TELEMETRY=False` to silence.
- **Ensemble retriever returns duplicate `(file, chunk_index=null)` + `(file, chunk_index=N)` rows** because BM25 indexes the full document while the dense store indexes individual chunks. Citations therefore contain near-duplicates. Worth deduping in Phase 3.
