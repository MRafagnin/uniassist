# UniAssist — Actions Required Before Implementation

Complete every item in this checklist before asking Copilot to start scaffolding the repo. Each section lists **what to do**, **why it's needed**, and **how to verify**.

---

## 1. Tooling

### 1.1 Python 3.11 — DONE

- **Status:** Python 3.11.9 installed and on PATH.
- **Verify:** `python --version` → `Python 3.11.x`.

### 1.2 `uv` (package manager) — DONE

- **Status:** `uv 0.11.15` installed.
- **Verify:** `uv --version` returns a version.

### 1.3 Git + GitHub CLI — DECIDED: skip `gh`

- **Status:** Git installed. `gh` install attempted via `winget install --id GitHub.cli` but failed with an `msstore` source certificate error (`0x8a15005e`).
- **Decision:** **skip `gh` entirely.** Use plain `git` against the HTTPS remote `https://github.com/MRafagnin/uniassist.git`. Authentication will go through Git Credential Manager (browser flow on first push).
- **Day-1 commands:**
  ```powershell
  git init -b main
  git remote add origin https://github.com/MRafagnin/uniassist.git
  git add .
  git commit -m "chore: initial scaffold"
  git push -u origin main
  ```

### 1.4 VS Code extensions (recommended)

- Python, Pylance, Ruff, GitLens, Markdown All in One.

---

## 2. Ollama models — DONE

All three models pulled and visible in `ollama list`:

- `qwen2.5:7b-instruct` (4.7 GB) — chat + triage generator
- `nomic-embed-text:latest` (274 MB) — embeddings (768-dim)
- `llama3.1:8b` (4.9 GB) — eval judge (separate from generator)

- **Verify:** `ollama list` shows all three.
- **Smoke test:** PASSED — `ollama run qwen2.5:7b-instruct "Reply with the word OK"` returned `OK`.
- **Smoke test:** `ollama run qwen2.5:7b-instruct "Reply with the word OK"` → returns `OK` within a few seconds.
- **Disk budget:** ~14 GB total. Confirm you have it free on the Ollama models drive.
- **RAM budget:** keep at least 10 GB free while running the 7–8B models. If your machine struggles, plan to swap chat model to `qwen2.5:3b-instruct` (note this in README later).

---

## 3. Knowledge-base corpus prep

### 3.1 Public web corpus (no action — the scraper handles it)

The scraper will crawl `https://www.sydney.edu.au/students/student-it.html`. **You don't need to do anything for this source.**

### 3.2 ServiceNow KB articles — NO MANUAL DOWNLOAD NEEDED

**Update:** the USYD Service Portal topic page and its KB articles are publicly accessible (no SSO). The scraper can crawl them directly.

- **Seed URL for the scraper:** `https://sydneyuni.service-now.com/sm?id=usyd_emp_taxonomy_topic&topic_id=4d7d2ae687d31dd0fb4dab0a0cbb3542`
- **Scraper behaviour to implement on Day 1:**
  - Treat the topic page as an index; follow links matching `id=kb_article*` or `id=usyd_emp_kb_article*`.
  - Render with a headless browser (Playwright) because the Service Portal is JS-driven — a plain `requests.get` will return an empty shell.
  - Stay on host `sydneyuni.service-now.com`; cap depth at 2 and max pages at ~60.
  - Save raw HTML to `data/raw_servicenow/` alongside the public web crawl in `data/raw_web/`.
- **Verified:** seed URL plus three sample KB articles load fully in an unauthenticated browser session:
  - <https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=b6022d07c36b79500b2b329f05013174>
  - <https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=012b5715c3579a90f1e6f5aa05013191>
  - <https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=b61bae5fc3ada294039f94ee0501312a>
- **Fallback:** if a specific article 403s anonymously during the crawl, fall back to saving it manually as "Webpage, HTML Only" into `data/raw_manual/` — but this should be the exception, not the plan.

### 3.3 Hand-written FAQ fallback — NOT NEEDED

Given §3.2, the hand-written markdown FAQ fallback is no longer in scope. Skip.

---

## 4. GitHub repo — DONE

- **Status:** repo created at <https://github.com/MRafagnin/uniassist> (public, empty).
- **Licence:** MIT (default) — will be written into `pyproject.toml` and `LICENSE` during scaffolding.
- **Day-1 wiring:** the local repo at `c:\dev\uniassist\` will be initialised with `git init`, the remote added as `origin` pointing at the URL above, and the first commit pushed to `main`. If `gh` is not yet installed by then, use plain `git remote add origin https://github.com/MRafagnin/uniassist.git`.

---

## 5. Eval Q&A seed — deferred until after ingestion

**Revised approach:** rather than hand-drafting 25 Q&A pairs up front, the eval set will be **derived from the scraped corpus** on Day 3, before the eval run:

- After ingestion completes (end of Day 1), the corpus content drives the question list — every Q maps to a real chunk that exists in the index, so we can never accidentally write a question the system *couldn't* answer even with a perfect retriever.
- **Process on Day 3 (~45 min):**
  1. List the top topics actually present in `data/raw_web/` + `data/raw_servicenow/` (Wi-Fi, VPN, M365, password, Canvas, Software, Printing, MFA, Hardware loan, etc.).
  2. For each topic, write 2–3 natural-language questions a student/staff member would ask, plus the source URL the answer should cite and 1–3 `must_contain` keywords pulled from the source text.
  3. Add 2–3 deliberately **out-of-scope** questions (e.g. "what time does Fisher Library close?") to exercise the refusal guardrail.
  4. Target **≥25 entries total**; save as `eval/qaset.yaml`.
- **Why this is fine (and arguably better):** grounding the eval in observed corpus content avoids the classic mistake of writing aspirational questions that the KB doesn't actually cover, which would make the retriever look worse than it is.
- **Risk:** if scraping yields very thin coverage on a category, the eval may not exercise it. Mitigation: review topic coverage at end of Day 1 and adjust scraper seeds before moving on.

---

## 6. Loom

- **Do:** Install the Loom desktop app (or use the Chrome extension) and sign in.
- **Verify:** record a 5-second test clip — confirms mic + screen capture both work.

---

## 7. Workspace cleanup — DONE

- **Status:** `c:\dev\uniassist\` already exists and is the active VS Code workspace, currently holding `role.md`, `plan.md`, and `prerequisites.md`. Scaffolding will add `pyproject.toml`, `src/`, `data/`, `eval/`, etc. into the same folder. The earlier `c:\dev\innovation-developer\` workspace is no longer used.

---

## 8. Time block

- **Do:** Block **two full days + one half-day** on your calendar. Splitting this across evenings will hurt quality and momentum.
- **Recommended split:** Day 1 (8h) ingestion + indexing; Day 2 (8h) RAG + triage + UI; Day 3 (4h) eval + README + Loom.

---

## Pre-flight checklist

- [x] Python 3.11 installed and on PATH (3.11.9)
- [x] `uv` installed (0.11.15)
- [x] Git installed; `gh` skipped by decision — plain `git` against `https://github.com/MRafagnin/uniassist.git`
- [x] `ollama list` shows `qwen2.5:7b-instruct`, `nomic-embed-text`, `llama3.1:8b`
- [x] Ollama smoke test: `qwen2.5:7b-instruct` returned `OK`
- [x] Public GitHub repo created: <https://github.com/MRafagnin/uniassist>
- [x] Licence chosen: MIT
- [x] ServiceNow KB confirmed publicly accessible (no SSO) — topic page + 3 sample KB articles verified anonymously
- [x] Eval Q&A seed strategy: derive from scraped corpus on Day 3 (no upfront drafting)
- [x] Loom installed and tested
- [x] Calendar blocked: 2 full days + half-day
- [x] Free disk ≥20 GB (C: has 355 GB free) and free RAM ≥10 GB (16 GB free of 32 GB total)
- [x] Workspace ready at `c:\dev\uniassist\`

**Only remaining item:** none — `gh` skipped by decision.

All go-criteria met. Reply **"go"** to start scaffolding and Phase 1.
