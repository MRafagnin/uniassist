"""BFS scraper for the University of Sydney student-IT pages.

Polite: respects robots.txt, fixed delay, same-domain only, capped depth + page count.
Writes raw HTML + a manifest.jsonl into ``data/raw/``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from selectolax.parser import HTMLParser

from uniassist.config import settings

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


def _slugify_url(url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    parsed = urlparse(url)
    tail = parsed.path.rstrip("/").rsplit("/", 1)[-1] or "index"
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in tail)[:60]
    return f"{safe}-{h}"


def _same_host(url: str, seed_host: str) -> bool:
    return urlparse(url).netloc == seed_host


def _path_allowed(url: str, prefixes: tuple[str, ...]) -> bool:
    """Restrict crawl to URLs whose path starts with one of the allowed prefixes."""
    if not prefixes:
        return True
    path = urlparse(url).path
    return any(path.startswith(p) for p in prefixes)


def _extract_links(html: str, base_url: str) -> list[str]:
    tree = HTMLParser(html)
    links: list[str] = []
    for a in tree.css("a[href]"):
        href = a.attributes.get("href", "")
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute, _ = urldefrag(urljoin(base_url, href))
        if absolute.startswith(("http://", "https://")):
            links.append(absolute)
    return links


def _load_robots(seed_url: str, user_agent: str) -> RobotFileParser:
    parsed = urlparse(seed_url)
    rp = RobotFileParser()
    rp.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
    try:
        rp.read()
    except Exception as exc:  # network failure -> be permissive but log
        log.warning("Could not load robots.txt: %s", exc)
    return rp


def crawl(
    seed_url: str | None = None,
    out_dir: Path | None = None,
    max_pages: int | None = None,
    max_depth: int | None = None,
    delay: float | None = None,
) -> Path:
    seed_url = seed_url or settings.scrape_seed_url
    out_dir = out_dir or settings.raw_dir
    max_pages = max_pages or settings.scrape_max_pages
    max_depth = max_depth or settings.scrape_max_depth
    delay = delay if delay is not None else settings.scrape_delay_seconds

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"

    seed_host = urlparse(seed_url).netloc
    robots = _load_robots(seed_url, settings.scrape_user_agent)

    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(seed_url, 0)])
    saved = 0

    headers = {"User-Agent": settings.scrape_user_agent}
    with (
        httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as client,
        manifest_path.open("w", encoding="utf-8") as manifest,
    ):
        while queue and saved < max_pages:
            url, depth = queue.popleft()
            if url in seen:
                continue
            seen.add(url)

            if not _same_host(url, seed_host):
                continue
            if not _path_allowed(url, settings.scrape_path_prefixes):
                continue
            if not robots.can_fetch(settings.scrape_user_agent, url):
                log.info("robots.txt disallows %s", url)
                continue

            try:
                resp = client.get(url)
            except httpx.HTTPError as exc:
                log.warning("GET failed %s: %s", url, exc)
                continue
            if resp.status_code != 200:
                log.info("Skipping %s (status %s)", url, resp.status_code)
                continue
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype not in ALLOWED_CONTENT_TYPES:
                continue

            slug = _slugify_url(url)
            html_path = out_dir / f"{slug}.html"
            html_path.write_text(resp.text, encoding="utf-8")
            manifest.write(
                json.dumps({"url": url, "file": html_path.name, "depth": depth}) + "\n"
            )
            saved += 1
            log.info("[%d/%d] saved %s", saved, max_pages, url)

            if depth < max_depth:
                for link in _extract_links(resp.text, url):
                    if link not in seen:
                        queue.append((link, depth + 1))

            time.sleep(delay)

    log.info("Scrape complete: %d pages -> %s", saved, out_dir)
    return manifest_path


if __name__ == "__main__":
    crawl()
