"""Loader for hand-dropped ServiceNow KB exports in ``data/raw_manual/``.

Accepts:
  - ``.html`` — saved-page exports from a browser. We parse with selectolax,
    strip ServiceNow chrome, derive title and (best-effort) source URL.
  - ``.md``   — passthrough; ``source_url`` taken from YAML frontmatter if present,
    else ``file://<absolute path>`` as a stable identifier.

Normalised output is written to ``data/processed/`` with ``source_type: servicenow_kb``.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from selectolax.parser import HTMLParser

from uniassist.config import settings
from uniassist.ingest.clean import MIN_BODY_CHARS, ProcessedDoc, _write_processed, html_to_markdown

log = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
KB_URL_PATTERNS = (
    re.compile(r'https?://[a-z0-9.-]*service-now\.com[^\s"\'<>]+', re.IGNORECASE),
)


def _extract_source_url(html: str, fallback: str) -> str:
    tree = HTMLParser(html)
    # 1) <link rel="canonical">
    link = tree.css_first('link[rel="canonical"]')
    if link and link.attributes.get("href"):
        return link.attributes["href"]
    # 2) <meta property="og:url">
    og = tree.css_first('meta[property="og:url"]')
    if og and og.attributes.get("content"):
        return og.attributes["content"]
    # 3) any service-now.com URL in the document
    for pat in KB_URL_PATTERNS:
        m = pat.search(html)
        if m:
            return m.group(0).rstrip('.,);')
    return fallback


def _parse_markdown_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta_block, body = m.group(1), m.group(2)
    meta: dict[str, str] = {}
    for line in meta_block.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def load_one(path: Path) -> ProcessedDoc | None:
    suffix = path.suffix.lower()
    fallback_url = path.resolve().as_uri()
    if suffix in (".html", ".htm"):
        html = path.read_text(encoding="utf-8", errors="ignore")
        source_url = _extract_source_url(html, fallback_url)
        title, body = html_to_markdown(html)
    elif suffix in (".md", ".markdown"):
        raw = path.read_text(encoding="utf-8")
        meta, body = _parse_markdown_frontmatter(raw)
        source_url = meta.get("source_url") or fallback_url
        title = meta.get("title") or path.stem.replace("-", " ").title()
        body = body.strip()
    else:
        return None

    if len(body) < MIN_BODY_CHARS:
        log.info("Skipping thin manual doc (%d chars): %s", len(body), path.name)
        return None

    out_path = settings.processed_dir / f"manual-{path.stem}.md"
    return ProcessedDoc(
        source_url=source_url,
        title=title,
        source_type="servicenow_kb",
        body_markdown=body,
        out_path=out_path,
    )


def load_all(manual_dir: Path | None = None) -> int:
    manual_dir = manual_dir or settings.raw_manual_dir
    if not manual_dir.exists():
        log.warning("No manual dir at %s — nothing to load.", manual_dir)
        return 0
    written = 0
    for path in sorted(manual_dir.iterdir()):
        if not path.is_file():
            continue
        try:
            doc = load_one(path)
        except Exception as exc:
            log.warning("Failed to parse %s: %s", path.name, exc)
            continue
        if doc is None:
            continue
        _write_processed(doc)
        written += 1
    log.info("Loaded %d manual KB docs -> %s", written, settings.processed_dir)
    return written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_all()
