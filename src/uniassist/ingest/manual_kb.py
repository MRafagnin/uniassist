"""Ingest ServiceNow KB articles into processed markdown.

Two complementary sources:

1. ``data/raw_servicenow/rendered/<sys_kb_id>.json`` — full article bodies
   captured by ``scripts/render_sn_kb.py`` via headless Chromium against the
   Service Portal. These give us real titles + real bodies + canonical URLs
   for every article whose ``sys_kb_id`` we know.
2. ``data/raw_manual/sn_top132.txt`` — the user-curated "top 132" listing.
   For any item in this file whose title doesn't match a rendered article
   we emit a title-only stub keyed on a Service Portal search URL.

Rendered articles always win; the manual list is just a coverage backstop.
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


def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower()).rstrip("?.! ")


def _topic_phrase(title: str) -> str:
    topic = re.sub(
        r"^(what\s+is(\s+the)?|what\s+are|how\s+do\s+i|how\s+to|how\s+can\s+i|"
        r"can\s+i|do\s+i|where\s+(is|are|do\s+i)|why\s+(is|are|do\s+i))\s+",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip().rstrip("?.! ").strip()
    return topic or title


def _load_rendered(rendered_dir: Path | None = None) -> list[dict]:
    rendered_dir = rendered_dir or (settings.raw_servicenow_dir / "rendered")
    out: list[dict] = []
    if not rendered_dir.exists():
        return out
    for path in sorted(rendered_dir.glob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log.warning("skip bad json: %s", path)
            continue
        if not rec.get("id") or not rec.get("title"):
            continue
        out.append(rec)
    return out


def parse_items(text: str) -> list[dict[str, str]]:
    """Parse the raw listing into a list of ``{title, body}`` records."""
    chunks = ITEM_RE.split(text)
    items: list[dict[str, str]] = []
    for i in range(1, len(chunks), 2):
        block = chunks[i + 1] if i + 1 < len(chunks) else ""
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].strip().lower() == "knowledge":
            lines = lines[1:]
        if not lines:
            continue
        title = lines[0].strip()
        body = " ".join(lines[1:]).strip()
        items.append({"title": title, "body": body})
    return items


def _render_full(rec: dict) -> tuple[str, str]:
    """Render a rendered-JSON record into (filename, markdown)."""
    title = rec["title"].strip()
    body = (rec.get("body") or "").strip()
    kb_id = rec["id"]
    url = ARTICLE_URL_TMPL.format(sys_kb_id=kb_id)
    topic = _topic_phrase(title)
    today = datetime.now(UTC).isoformat()

    parts: list[str] = [f"# {title}", ""]
    parts.append(f"**Topic:** {topic}")
    parts.append("")
    parts.append(
        f"This University of Sydney ICT knowledge-base article — titled "
        f"\"{title}\" — covers {topic}."
    )
    parts.append("")
    if body:
        parts.append(body)
        parts.append("")
    parts.append(
        f"**Keywords:** {topic}; {title}; University of Sydney; ICT; "
        "knowledge base; ServiceNow."
    )
    parts.append("")
    parts.append(f"Source: [{title}]({url})")
    body_md = "\n".join(parts).strip() + "\n"

    frontmatter = (
        "---\n"
        f"source_url: {url}\n"
        f"title: {json.dumps(title)}\n"
        "source_type: servicenow_kb\n"
        f"kb_id: {kb_id}\n"
        "has_body: true\n"
        f"body_chars: {len(body)}\n"
        f"processed_at: {today}\n"
        "---\n\n"
    )
    fname = f"sn-{kb_id}.md"
    return fname, frontmatter + body_md


def _render_stub(item: dict[str, str], kb_id: str | None) -> tuple[str, str]:
    title = item["title"].strip()
    body = item.get("body", "").strip()
    url = (
        ARTICLE_URL_TMPL.format(sys_kb_id=kb_id)
        if kb_id
        else SEARCH_URL_TMPL.format(q=quote_plus(title))
    )
    topic = _topic_phrase(title)
    today = datetime.now(UTC).isoformat()
    parts: list[str] = [f"# {title}", ""]
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
    fname = f"mn-{_slug(title)}.md"
    return fname, frontmatter + body_md


def ingest(
    source: Path | None = None,
    processed_dir: Path | None = None,
    rendered_dir: Path | None = None,
) -> int:
    src = source or (settings.raw_manual_dir / "sn_top132.txt")
    out_dir = processed_dir or settings.processed_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write a full-body doc for every rendered article.
    rendered = _load_rendered(rendered_dir)
    rendered_titles: set[str] = set()
    written = 0
    for rec in rendered:
        fname, md = _render_full(rec)
        (out_dir / fname).write_text(md, encoding="utf-8")
        rendered_titles.add(_norm_title(rec["title"]))
        written += 1
    log.info("Wrote %d rendered SN KB docs", written)

    # 2. Stubs for any items in the manual top-N list that we haven't rendered.
    if src.exists():
        items = parse_items(src.read_text(encoding="utf-8"))
        stubs = 0
        for item in items:
            if _norm_title(item["title"]) in rendered_titles:
                continue
            fname, md = _render_stub(item, kb_id=None)
            (out_dir / fname).write_text(md, encoding="utf-8")
            stubs += 1
        log.info("Wrote %d stubs for non-rendered manual titles", stubs)
        written += stubs
    else:
        log.warning("Manual KB source not found: %s", src)

    log.info("Total manual_kb docs written: %d -> %s", written, out_dir)
    return written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ingest()
