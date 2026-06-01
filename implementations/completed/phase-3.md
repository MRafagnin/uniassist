# Phase 3 — Streamlit UI + carry-forward polish

**Status:** ✅ Completed — June 2026
**Branch:** `phase-3-ui`

> Deviation from plan: `Settings.retrieval_k` shipped as `2` (not `3`) to hold `/chat` P50 under the latency target on CPU. Eval pins `k=5` independently.

Build the three-tab Streamlit UI (`Chat | Triage | Metrics`) on top of the FastAPI + SQLite stack shipped in Phase 2, and clear the two Phase-2 carry-forwards that materially improve the demo (`k=3`, citation dedupe). UI talks to FastAPI over HTTP via `httpx`. Chat history lives in `st.session_state` only.

---

## Decisions (locked)

- **UI ↔ backend transport:** Streamlit → FastAPI over `httpx` (sync, `localhost:8000`). Proves the API and matches the planned architecture.
- **Chat history:** `st.session_state["messages"]` only; cleared on reload. No new DB table.
- **Carry-forwards in scope:** trim ensemble retrieval to `k=3` (settings default) + dedupe citations in `rag.chain` (collapse rows sharing the same `metadata["file"]`, keep the highest-rank entry, renumber `[n]` from 1).
- **Carry-forwards deferred:** Chroma telemetry warning (cosmetic), token estimates, eval-faithfulness widget.
- **Metrics tab:** purely from `GET /metrics` + a new `GET /recent` — no direct SQLite reads from the UI (keeps the Streamlit process API-only).
- **Out of scope:** streaming responses, multi-turn server memory, conversation persistence, auth, eval harness automation, README case-study rewrite (all Phase 4).

---

## Sub-phases

### 3A — Backend touch-ups (land first, unlocks UI)

1. **Trim retrieval default** — `Settings.retrieval_k: int = 3` in [src/uniassist/config.py](../src/uniassist/config.py). Verify [eval/run_eval.py](../eval/run_eval.py) doesn't depend on the previous default; if it does, pin `k=5` there explicitly.
2. **Dedupe citations** — in [src/uniassist/rag/chain.py](../src/uniassist/rag/chain.py) `answer()`, add `_dedupe_docs(docs)` that collapses entries sharing `metadata["file"]`, keeping the first occurrence (highest ensemble rank). Call it before `format_docs` / `_docs_to_citations`. `[n]` renumbers from 1.
3. **`GET /recent` endpoint** — in [src/uniassist/api.py](../src/uniassist/api.py), `@app.get("/recent")` returning `logging_store.recent(limit)` with `limit: int = Query(20, ge=1, le=200)`. Used by the Metrics tab.
4. **Tests** — extend [tests/test_rag_chain.py](../tests/test_rag_chain.py) with a dedupe case (two docs same `file`, one `chunk_index=None`, one `chunk_index=2` → single citation `n=1`, order preserved). Add `test_recent_endpoint` to [tests/test_api.py](../tests/test_api.py) (monkeypatch `logging_store.recent`, assert 200 + list shape).

### 3B — UI shell + HTTP client (parallel with 3A after step 1)

5. **HTTP client** — new `src/uniassist/ui/client.py`: thin wrapper around `httpx.Client(base_url=API_BASE, timeout=180.0)` with `chat(question)`, `triage(ticket_text)`, `metrics()`, `recent(limit)`, `healthz()`. `API_BASE = os.getenv("UNIASSIST_API", "http://localhost:8000")`. Non-2xx raises typed `APIError(status, body)`.
6. **App scaffold** — rewrite [src/uniassist/ui/app.py](../src/uniassist/ui/app.py): `st.set_page_config(page_title="UniAssist", layout="wide")`, top-of-page health badge from `/healthz` (`✅ API · chat: qwen2.5:7b-instruct · 1,251 docs` green / `❌ API unreachable` red with hint), `st.tabs(["Chat", "Triage", "Metrics"])`. Small CSS block for source-type chip colours.

### 3C — Chat tab

7. **Chat state** — `st.session_state.messages: list[{role, content, citations?, latency_ms?}]` initialised once. Sidebar **Clear conversation** button.
8. **Render loop** — iterate history with `st.chat_message(role)`. Assistant turns render Markdown `content`, then a `st.caption` row with `⏱ {latency_ms} ms`, then a **Sources** `st.expander` listing each citation as `[n] {title}` linking to `source_url` with a coloured chip per `source_type` (`Web` = blue, `ServiceNow KB` = orange, `Manual` = grey).
9. **Input + call** — `st.chat_input("Ask about IT, accounts, WiFi…")`; on submit: append user turn, `with st.spinner("Thinking…"): client.chat(q)`, append assistant turn, `st.rerun()`.

### 3D — Triage tab

10. **Form** — `st.text_area("Ticket text", height=180)` + `st.button("Triage", type="primary")`; submit → `with st.spinner("Classifying…"): client.triage(text)`.
11. **Render result** — two-column layout. Left: `st.metric("Category", result.category)`, `st.metric("Priority", result.priority)`, `st.metric("Queue", result.suggested_queue)`. Right: `st.progress(result.confidence)` + numeric, then `st.markdown("**Rationale**\n\n" + result.rationale)`. Raw JSON inside `st.expander("Raw response")` with `st.json(...)`.

### 3E — Metrics tab

12. **Fetch** — `client.metrics()` + `client.recent(20)`; Refresh button in tab header (`st.button("Refresh") → st.rerun()`).
13. **Top row** — three `st.metric` widgets: total chat calls, total triage calls, overall P50 latency (ms).
14. **Latency chart** — `st.bar_chart` of per-endpoint P50/P95 from the `latency_ms` dict.
15. **Top categories** — `st.bar_chart` over `summary["top_categories"]` (label → count).
16. **Recent queries** — `st.dataframe` with columns `ts, endpoint, input_redacted` (truncated 80 chars), `latency_ms`. Visually confirms PII redaction.

### 3F — Run script + smoke + docs

17. **`run.ps1`** — optional `dev` task printing the two-terminal instruction (`run.ps1 api` / `run.ps1 ui`). No process management.
18. **Manual smoke** (recorded in PR description): start API, start UI, WiFi question → cited answer; VPN triage → `category=VPN`; metrics populates; out-of-scope question → refusal + empty citations.
19. **README** — short Phase-3 section + optional `docs/screenshots/{chat,triage,metrics}.png`. Full case-study rewrite stays in Phase 4.

---

## Execution order

1. **3A** (small + independent) — lands first so the UI consumes the polished API.
2. **3B → 3C → 3D → 3E** — sequential within UI; each tab self-contained.
3. **3F** at the end.
4. Single PR `phase-3-ui` → `main`. Commits: `feat(rag): dedupe citations + k=3`, `feat(api): /recent`, `feat(ui): chat tab`, `feat(ui): triage tab`, `feat(ui): metrics tab`, `docs: phase 3`.

---

## Relevant files

- [src/uniassist/config.py](../src/uniassist/config.py) — `retrieval_k` 5 → 3.
- [src/uniassist/rag/chain.py](../src/uniassist/rag/chain.py) — add `_dedupe_docs`, call from `answer()`.
- [src/uniassist/api.py](../src/uniassist/api.py) — add `GET /recent`.
- [src/uniassist/logging_store.py](../src/uniassist/logging_store.py) — already provides `recent(n)` + `summary()`; no change.
- [src/uniassist/ui/client.py](../src/uniassist/ui/client.py) — **new**, `httpx` wrapper.
- [src/uniassist/ui/app.py](../src/uniassist/ui/app.py) — replace placeholder with three-tab app.
- [tests/test_rag_chain.py](../tests/test_rag_chain.py) — dedupe case.
- [tests/test_api.py](../tests/test_api.py) — `/recent` case.
- [run.ps1](../run.ps1) — optional `dev` helper.
- `docs/screenshots/{chat,triage,metrics}.png` — optional, for README.

---

## Verification

1. `uv run ruff check .` clean.
2. `uv run pytest -q` green; expected delta `+2` tests (dedupe + `/recent`).
3. With API + UI running:
   - `curl localhost:8000/recent?limit=5` → JSON array.
   - Streamlit health badge green; tabs render.
   - **Chat:** "How do I connect to UniWiFi?" → answer with `[1]…[n]` citations, Sources expander lists each as a working link with a source-type chip; no two citations share the same `file`; latency caption present.
   - **Chat:** "What's the weather?" → refusal text, no citations, <10 s wall clock (no LLM call).
   - **Triage:** "My VPN keeps dropping every 10 minutes" → `category=VPN`, priority P1–P4, confidence bar, rationale, raw-JSON expander.
   - **Metrics:** three top-of-tab `st.metric`s populated; latency + category bar charts render; recent-queries dataframe shows a row containing `[REDACTED_EMAIL]` after a chat with `student@uni.edu.au`.
4. **Latency:** `/chat` P50 < 60 s on CPU after `k=3` (baseline 70–150 s). Record before/after in PR description.
5. **API-down behaviour:** red badge + each tab shows `st.error("API unreachable at … — start it with run.ps1 api")` instead of crashing.

---

## Risks & mitigations

- **`httpx` default timeout (5 s) trips on cold LLM calls** → set `timeout=180.0` on the client.
- **`st.rerun()` loops on submit** → use the `if prompt := st.chat_input(...)` pattern and only rerun after appending the assistant turn.
- **Citation dedupe drops a useful chunk** → keep the first occurrence by ensemble rank (BM25 full-doc usually ranks broader hits higher); unit test asserts ordering preserved.
- **`k=3` hurts retrieval@5 in eval** → eval owns its own `k`; pin to 5 in `eval/run_eval.py` if the change leaks (check during step 1).

---

## Out of scope (Phase 4)

- Eval harness + faithfulness judge, README case-study rewrite, Loom video.
- Streaming responses, multi-turn server memory, conversation persistence.
- Auth, ServiceNow API integration.
- Chroma telemetry suppression, token estimates.
