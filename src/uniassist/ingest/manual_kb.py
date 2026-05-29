"""Ingest the user-curated ServiceNow "top 132 KB" listing.

The Service Portal API publicly exposes only ~12 KB cards per topic page
(``servicenow_scraper.py``). The remainder of the popular KB titles — and
short bodies for the ones whose summary the portal renders inline — were
captured manually in ``data/raw_manual/sn_top132.txt``.

This module parses that file into one markdown doc per article so the RAG
index has coverage for the whole top-132 list, not just the 12 we can hit
via the public API. For the 12 articles we already know the ``sys_kb_id``
for (via the SN manifest), we use the direct article URL; for the rest we
emit a Service Portal search URL keyed on the title — which is a working
public landing page that lets the user click through to the right article.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus

from uniassist.config import settings

log = logging.getLogger(__name__)

SERVICENOW_HOST = "sydneyuni.service-now.com"
BASE_URL = f"https://{SERVICENOW_HOST}"
ARTICLE_URL_TMPL = f"{BASE_URL}/sm?id=kb_article_view&sys_kb_id={{sys_kb_id}}"
SEARCH_URL_TMPL = f"{BASE_URL}/sm?id=search&q={{q}}"

ITEM_RE = re.compile(r"^Item\s+(\d+)\s+of\s+\d+,\s*$", re.MULTILINE)


def _slug(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]
    if not base:
        base = "kb"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


def _load_manifest(processed_dir: Path | None = None) -> dict[str, str]:
    """Map normalised title -> sys_kb_id from the SN scraper manifest."""
    raw_dir = settings.raw_servicenow_dir
    manifest = raw_dir / "manifest.jsonl"
    out: dict[str, str] = {}
    if not manifest.exists():
        return out
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        title = (rec.get("title") or "").strip().lower()
        kb_id = rec.get("kb_id") or ""
        if title and kb_id:
            out[title] = kb_id
    return out


def parse_items(text: str) -> list[dict[str, str]]:
    """Parse the raw listing into a list of ``{title, body}`` records."""
    # split on "Item N of M," lines
    chunks = ITEM_RE.split(text)
    # chunks layout: [preamble, num, block, num, block, ...]
    items: list[dict[str, str]] = []
    for i in range(1, len(chunks), 2):
        block = chunks[i + 1] if i + 1 < len(chunks) else ""
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        # first non-empty line is "Knowledge"
        if lines[0].strip().lower() == "knowledge":
            lines = lines[1:]
        if not lines:
            continue
        title = lines[0].strip()
        body = " ".join(lines[1:]).strip()
        items.append({"title": title, "body": body})
    return items


def _render(item: dict[str, str], kb_id: str | None) -> str:
    title = item["title"]
    body = item["body"]
    if kb_id:
        url = ARTICLE_URL_TMPL.format(sys_kb_id=kb_id)
    else:
        url = SEARCH_URL_TMPL.format(q=quote_plus(title))
    today = datetime.now(UTC).isoformat()
    parts: list[str] = [f"# {title}", ""]
    # Topic phrase: title without "What is" / "How do I" prefixes
    topic = re.sub(
        r"^(what\s+is(\s+the)?|what\s+are|how\s+do\s+i|how\s+to|how\s+can\s+i|"
        r"can\s+i|do\s+i|where\s+(is|are|do\s+i)|why\s+(is|are|do\s+i))\s+",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip().rstrip("?.! ").strip() or title
    parts.append(f"**Topic:** {topic}")
    parts.append("")
    parts.append(
        f"This University of Sydney ICT knowledge-base article — titled "
        f"\"{title}\" — covers {topic}. Use it for questions about {topic} "
        f"at the University of Sydney."
    )
    parts.append("")
    if body:
        parts.append(body)
        parts.append("")
    parts.append(f"**Keywords:** {topic}; {title}; University of Sydney; ICT; knowledge base.")
    parts.append("")
    parts.append(f"Read the full article here: [{title}]({url})")
    parts.append("(UniKey sign-in may be required to view the full instructions.)")
    body_md = "\n".join(parts).strip() + "\n"
    frontmatter = (
        "---\n"
        f"source_url: {url}\n"
        f"title: {json.dumps(title)}\n"
        "source_type: servicenow_kb\n"
        f"kb_id: {kb_id or ''}\n"
        f"has_body: {'true' if body else 'false'}\n"
        f"processed_at: {today}\n"
        "---\n\n"
    )
    return frontmatter + body_md


def ingest(
    source: Path | None = None,
    processed_dir: Path | None = None,
) -> int:
    src = source or (settings.raw_manual_dir / "sn_top132.txt")
    out_dir = processed_dir or settings.processed_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        log.warning("Manual KB source not found: %s", src)
        return 0

    title_to_kb = _load_manifest(out_dir)
    items = parse_items(src.read_text(encoding="utf-8"))
    log.info("Parsed %d items from %s (manifest has %d direct links)", len(items), src.name, len(title_to_kb))

    written = 0
    for item in items:
        kb_id = title_to_kb.get(item["title"].strip().lower())
        md = _render(item, kb_id)
        out_path = out_dir / f"mn-{_slug(item['title'])}.md"
        out_path.write_text(md, encoding="utf-8")
        written += 1
    log.info("Wrote %d manual KB docs -> %s", written, out_dir)
    return written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ingest()
