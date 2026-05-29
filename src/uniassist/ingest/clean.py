"""HTML -> clean markdown with YAML-ish frontmatter.

Reads scraped HTML from ``data/raw/`` (driven by ``manifest.jsonl``) and writes
normalised markdown files to ``data/processed/``. Drops pages with <200 chars of
extracted body text.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from markdownify import markdownify as md
from selectolax.parser import HTMLParser

from uniassist.config import settings

log = logging.getLogger(__name__)

MIN_BODY_CHARS = 200
DROP_SELECTORS = (
    "script", "style", "noscript", "nav", "footer", "header",
    "aside", "form", "[role=navigation]", "[role=banner]",
    "[role=contentinfo]", ".cookie", ".breadcrumb",
)
MAIN_SELECTORS = ("main", "article", "[role=main]", "#main", "#content")


@dataclass
class ProcessedDoc:
    source_url: str
    title: str
    source_type: str
    body_markdown: str
    out_path: Path


def _extract_title(tree: HTMLParser) -> str:
    for sel in ("h1", "title"):
        node = tree.css_first(sel)
        if node and node.text(strip=True):
            return node.text(strip=True)
    return "(untitled)"


def _extract_main_html(tree: HTMLParser) -> str:
    for sel in MAIN_SELECTORS:
        node = tree.css_first(sel)
        if node:
            return node.html or ""
    body = tree.css_first("body")
    return (body.html if body else tree.html) or ""


def html_to_markdown(html: str) -> tuple[str, str]:
    """Return (title, body_markdown). Pure function for testability."""
    tree = HTMLParser(html)
    for sel in DROP_SELECTORS:
        for node in tree.css(sel):
            node.decompose()
    title = _extract_title(tree)
    main_html = _extract_main_html(tree)
    body = md(main_html, heading_style="ATX", strip=["a"]).strip() if main_html else ""
    # Collapse runs of blank lines
    lines = [ln.rstrip() for ln in body.splitlines()]
    deduped: list[str] = []
    blank = 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank <= 1:
                deduped.append(ln)
        else:
            blank = 0
            deduped.append(ln)
    return title, "\n".join(deduped).strip()


def _write_processed(doc: ProcessedDoc) -> None:
    doc.out_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"source_url: {doc.source_url}\n"
        f"title: {json.dumps(doc.title)}\n"
        f"source_type: {doc.source_type}\n"
        f"processed_at: {datetime.now(UTC).isoformat()}\n"
        "---\n\n"
    )
    doc.out_path.write_text(frontmatter + doc.body_markdown + "\n", encoding="utf-8")


def clean_all(
    raw_dir: Path | None = None,
    processed_dir: Path | None = None,
    source_type: str = "web",
) -> int:
    raw_dir = raw_dir or settings.raw_dir
    processed_dir = processed_dir or settings.processed_dir
    manifest = raw_dir / "manifest.jsonl"
    if not manifest.exists():
        log.warning("No manifest at %s — nothing to clean.", manifest)
        return 0

    written = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        html_path = raw_dir / entry["file"]
        if not html_path.exists():
            continue
        title, body = html_to_markdown(html_path.read_text(encoding="utf-8"))
        if len(body) < MIN_BODY_CHARS:
            log.info("Skipping thin page (%d chars): %s", len(body), entry["url"])
            continue
        out_path = processed_dir / f"{html_path.stem}.md"
        _write_processed(
            ProcessedDoc(
                source_url=entry["url"],
                title=title,
                source_type=source_type,
                body_markdown=body,
                out_path=out_path,
            )
        )
        written += 1

    log.info("Cleaned %d documents -> %s", written, processed_dir)
    return written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    clean_all()
