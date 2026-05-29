"""Render all ServiceNow KB articles via headless Playwright and save title+body JSON.

Reads sys_kb_ids from data/raw_servicenow/sn_ids.txt.
Writes data/raw_servicenow/rendered/<id>.json with {id, url, title, body, fetched_at}.
Skips ids already rendered (resumable).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
IDS_FILE = ROOT / "data" / "raw_servicenow" / "sn_ids.txt"
OUT_DIR = ROOT / "data" / "raw_servicenow" / "rendered"
URL_TMPL = "https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id={id}"

CONCURRENCY = 4
NAV_TIMEOUT_MS = 45000
SELECTOR_TIMEOUT_MS = 8000

BODY_SELECTORS = [
    ".kb-article-content",
    "[ng-bind-html]",
    ".kb-article",
    "article",
    ".sp-rich-text",
]
TITLE_SELECTORS = [
    ".kb-article-title",
    "h1.kb-title",
    "h1",
    ".sp-page-title",
]


async def render_one(context, kb_id: str) -> dict:
    url = URL_TMPL.format(id=kb_id)
    page = await context.new_page()
    try:
        resp = await page.goto(url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
        status = resp.status if resp else None
        with contextlib.suppress(Exception):
            await page.wait_for_selector(",".join(BODY_SELECTORS), timeout=SELECTOR_TIMEOUT_MS)
        extracted = await page.evaluate(
            """(args) => {
                const bodySel = args.body;
                const titleSel = args.title;
                let body = {selector: null, text: ''};
                for (const s of bodySel) {
                    const el = document.querySelector(s);
                    if (el && el.innerText && el.innerText.trim().length > 50) {
                        body = {selector: s, text: el.innerText.trim()};
                        break;
                    }
                }
                let title = '';
                for (const s of titleSel) {
                    const el = document.querySelector(s);
                    if (el && el.innerText && el.innerText.trim()) {
                        title = el.innerText.trim();
                        break;
                    }
                }
                if (!title) title = (document.title || '').replace(/\\s*\\|\\s*Sydney.*/i, '').trim();
                return {title, body_selector: body.selector, body: body.text};
            }""",
            {"body": BODY_SELECTORS, "title": TITLE_SELECTORS},
        )
        return {
            "id": kb_id,
            "url": url,
            "status": status,
            "title": extracted.get("title") or "",
            "body": extracted.get("body") or "",
            "body_selector": extracted.get("body_selector"),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
    finally:
        await page.close()


async def worker(name: int, context, queue: asyncio.Queue, results: list, errors: list):
    while True:
        kb_id = await queue.get()
        if kb_id is None:
            queue.task_done()
            return
        out_path = OUT_DIR / f"{kb_id}.json"
        if out_path.exists():
            queue.task_done()
            continue
        try:
            rec = await render_one(context, kb_id)
            out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append(kb_id)
            status = rec.get("status")
            body_len = len(rec.get("body") or "")
            print(f"[w{name}] {kb_id} status={status} body={body_len} title={rec.get('title')!r}", flush=True)
        except Exception as exc:
            errors.append((kb_id, str(exc)))
            print(f"[w{name}] ERROR {kb_id}: {exc}", flush=True)
        finally:
            queue.task_done()


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ids = [ln.strip() for ln in IDS_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"total ids: {len(ids)}", flush=True)
    pending = [i for i in ids if not (OUT_DIR / f"{i}.json").exists()]
    print(f"pending: {len(pending)} (skipping {len(ids) - len(pending)} cached)", flush=True)
    if not pending:
        return

    queue: asyncio.Queue = asyncio.Queue()
    for i in pending:
        queue.put_nowait(i)
    for _ in range(CONCURRENCY):
        queue.put_nowait(None)

    results: list = []
    errors: list = []
    t0 = time.time()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        )
        workers = [asyncio.create_task(worker(i, context, queue, results, errors)) for i in range(CONCURRENCY)]
        await queue.join()
        await asyncio.gather(*workers)
        await browser.close()
    dt = time.time() - t0
    print(f"done in {dt:.1f}s — ok={len(results)} err={len(errors)}", flush=True)
    if errors:
        for kb_id, msg in errors[:20]:
            print(f"  {kb_id}: {msg}", flush=True)
        sys.exit(2 if len(errors) > len(pending) * 0.2 else 0)


if __name__ == "__main__":
    asyncio.run(main())
