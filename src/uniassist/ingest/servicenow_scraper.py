"""ServiceNow Service Portal KB harvester.

The USYD Service Portal renders KB articles via an Angular SPA that gates the
article *body* behind UniKey/Okta SSO when no session is present. The
**title, KB number, category and URL** of each public KB are still available
without auth via the Service Portal page API:

    GET /api/now/sp/page?id=<page_id>&topic_id=<topic_id>
    GET /api/now/sp/page?id=kb_article_view&sys_kb_id=<sys_kb_id>

Per UniAssist's "concierge" use case (point students/staff at the right
article instead of re-explaining its contents) we capture exactly that:
short stubs with title + category breadcrumb + canonical link, written
straight into ``data/processed/`` so they flow into the index alongside the
sydney.edu.au pages.

Output mirrors :mod:`uniassist.ingest.clean`'s frontmatter so
:mod:`build_index` picks them up unchanged.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from uniassist.config import settings

log = logging.getLogger(__name__)

SERVICENOW_HOST = "sydneyuni.service-now.com"
BASE_URL = f"https://{SERVICENOW_HOST}"
SEED_URL = (
    f"{BASE_URL}/sm?id=usyd_emp_taxonomy_topic"
    "&topic_id=4d7d2ae687d31dd0fb4dab0a0cbb3542"
)
KB_ARTICLE_RE = re.compile(r"id=kb_article_view", re.IGNORECASE)

# Default taxonomy seeds. Each is (page_id, topic_id). Add more as needed.
DEFAULT_TOPIC_SEEDS: tuple[tuple[str, str], ...] = (
    ("usyd_emp_taxonomy_topic", "4d7d2ae687d31dd0fb4dab0a0cbb3542"),  # Technology
)

ARTICLE_URL_TMPL = f"{BASE_URL}/sm?id=kb_article_view&sys_kb_id={{sys_kb_id}}"
HEADERS = {
    "Accept": "application/json",
    "X-UserToken": "Anonymous",
    "User-Agent": "Mozilla/5.0 (compatible; UniAssistBot/0.1)",
}


def _slug_for(url: str) -> str:
    """Stable, filesystem-safe slug derived from the KB URL."""
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    qs = parse_qs(urlparse(url).query)
    kb_id = (qs.get("sys_kb_id") or qs.get("topic_id") or [""])[0][:24]
    return f"sn-{kb_id or 'page'}-{h}"


def _is_servicenow(url: str) -> bool:
    return urlparse(url).netloc == SERVICENOW_HOST


def _get_json(client: httpx.Client, url: str) -> dict[str, Any] | None:
    try:
        r = client.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed GET %s: %s", url, exc)
        return None


def _walk_kb_cards(node: Any) -> list[dict[str, Any]]:
    """Recursively find every kbCardData dict in a topic-page JSON tree."""
    found: list[dict[str, Any]] = []

    def visit(n: Any) -> None:
        if isinstance(n, dict):
            if "kbCardData" in n and isinstance(n["kbCardData"], dict):
                found.append(n["kbCardData"])
            for v in n.values():
                visit(v)
        elif isinstance(n, list):
            for v in n:
                visit(v)

    visit(node)
    return found


def _walk_subtopics(node: Any) -> list[str]:
    """Find topic_ids of subtopics referenced by a topic page."""
    ids: list[str] = []

    def visit(n: Any) -> None:
        if isinstance(n, dict):
            if "subTopics" in n and isinstance(n["subTopics"], list):
                for s in n["subTopics"]:
                    tid = s.get("topic_id") or s.get("sys_id")
                    if tid:
                        ids.append(tid)
            for v in n.values():
                visit(v)
        elif isinstance(n, list):
            for v in n:
                visit(v)

    visit(node)
    return ids


def _fetch_article_category(client: httpx.Client, sys_kb_id: str) -> str:
    """Pull the breadcrumb-style description from the article page metatags."""
    result = _get_json(
        client,
        f"{BASE_URL}/api/now/sp/page?id=kb_article_view&sys_kb_id={sys_kb_id}",
    )
    if not result:
        return ""
    for tag in result.get("metatags", []) or []:
        if tag.get("name") == "description":
            return (tag.get("content") or "").strip(" -")
    return ""


# Generic question prefixes that drown out the actual subject when titles
# like "What is Zoom Videoconferencing?" are embedded — we strip them to get
# a "topic phrase" that we repeat in the body for retrieval signal.
_TITLE_PREFIX_RE = re.compile(
    r"^(what\s+is(\s+the)?|what\s+are|how\s+do\s+i|how\s+to|how\s+can\s+i|"
    r"can\s+i|do\s+i|where\s+(is|are|do\s+i)|why\s+(is|are|do\s+i))\s+",
    re.IGNORECASE,
)


def _topic_phrase(title: str) -> str:
    """Strip generic question prefixes and trailing punctuation from a title."""
    phrase = _TITLE_PREFIX_RE.sub("", title).strip()
    return phrase.rstrip("?.! ").strip() or title


def _render_stub(
    *,
    title: str,
    article_url: str,
    sys_kb_id: str,
    category: str,
    kb_number: str = "",
) -> str:
    today = datetime.now(UTC).isoformat()
    topic = _topic_phrase(title)
    # Make the topic noun the dominant token in the body so retrieval matches
    # on the article's subject. Boilerplate is pushed to a single short line
    # at the end so it doesn't drown out the topic across 12+ stubs.
    parts = [f"# {title}", ""]
    parts.append(f"**{topic}**")
    parts.append("")
    parts.append(f"{topic} at the University of Sydney.")
    parts.append(f"This article answers: {title}")
    if category:
        parts.append(f"Category: {category}.")
    parts += [
        "",
        f"Read the full article on {topic} here: [{title}]({article_url})",
        "(UniKey sign-in may be required to view the full instructions.)",
    ]
    if kb_number:
        parts.append("")
        parts.append(f"Knowledge article ID: {kb_number}")
    body = "\n".join(parts).strip() + "\n"
    frontmatter = (
        "---\n"
        f"source_url: {article_url}\n"
        f"title: {json.dumps(title)}\n"
        f"source_type: servicenow_kb\n"
        f"kb_id: {sys_kb_id}\n"
        f"category: {json.dumps(category)}\n"
        f"processed_at: {today}\n"
        "---\n\n"
    )
    return frontmatter + body


def crawl(
    topic_seeds: tuple[tuple[str, str], ...] = DEFAULT_TOPIC_SEEDS,
    processed_dir: Path | None = None,
    raw_dir: Path | None = None,
    max_articles: int = 200,
    delay_seconds: float = 0.5,
    fetch_categories: bool = True,
) -> int:
    """Crawl topic seeds, write one stub markdown per KB article. Returns count."""
    processed_dir = processed_dir or settings.processed_dir
    raw_dir = raw_dir or settings.raw_servicenow_dir
    processed_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.jsonl"

    seen_kb: set[str] = set()
    seen_topic: set[str] = set()
    written = 0

    with (
        httpx.Client(follow_redirects=True) as client,
        manifest_path.open("w", encoding="utf-8") as manifest,
    ):
        pending: list[tuple[str, str]] = list(topic_seeds)
        while pending and written < max_articles:
            page_id, topic_id = pending.pop(0)
            if topic_id in seen_topic:
                continue
            seen_topic.add(topic_id)

            log.info("Topic: %s id=%s", page_id, topic_id)
            result = _get_json(
                client,
                f"{BASE_URL}/api/now/sp/page?id={page_id}&topic_id={topic_id}",
            )
            if not result:
                continue

            for tid in _walk_subtopics(result):
                if tid not in seen_topic:
                    pending.append((page_id, tid))

            cards = _walk_kb_cards(result)
            log.info("  Found %d KB cards on this topic.", len(cards))
            for card in cards:
                if written >= max_articles:
                    break
                title = (card.get("title") or "").strip()
                rel_url = (card.get("url") or "").strip()
                if not (title and rel_url):
                    continue
                qs = parse_qs(urlparse(rel_url).query)
                sys_kb_id = (qs.get("sys_kb_id") or [""])[0]
                if not sys_kb_id or sys_kb_id in seen_kb:
                    continue
                seen_kb.add(sys_kb_id)

                article_url = ARTICLE_URL_TMPL.format(sys_kb_id=sys_kb_id)
                category = ""
                if fetch_categories:
                    category = _fetch_article_category(client, sys_kb_id)
                    time.sleep(delay_seconds)

                stub = _render_stub(
                    title=title,
                    article_url=article_url,
                    sys_kb_id=sys_kb_id,
                    category=category,
                    kb_number=card.get("number", "") or "",
                )
                slug = _slug_for(article_url)
                out_path = processed_dir / f"{slug}.md"
                out_path.write_text(stub, encoding="utf-8")
                manifest.write(
                    json.dumps(
                        {
                            "url": article_url,
                            "file": out_path.name,
                            "title": title,
                            "kb_id": sys_kb_id,
                            "category": category,
                        }
                    )
                    + "\n"
                )
                manifest.flush()
                written += 1
                log.info("  [%d] %s", written, title)

    log.info("ServiceNow harvest complete: %d KB stubs -> %s", written, processed_dir)
    return written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    crawl()
