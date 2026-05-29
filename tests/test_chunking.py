from pathlib import Path

from uniassist.ingest.build_index import _parse_doc

SAMPLE = """---
source_url: https://example.test/foo
title: "Foo Bar"
source_type: web
---

# Foo Bar

Body paragraph one.

## Section

Body paragraph two.
"""


def test_parse_doc_extracts_frontmatter_and_body(tmp_path: Path):
    f = tmp_path / "foo.md"
    f.write_text(SAMPLE, encoding="utf-8")
    meta, body = _parse_doc(f)
    assert meta["source_url"] == "https://example.test/foo"
    assert meta["title"] == "Foo Bar"
    assert meta["source_type"] == "web"
    assert body.startswith("# Foo Bar")
    assert "Body paragraph two" in body


def test_parse_doc_handles_missing_frontmatter(tmp_path: Path):
    f = tmp_path / "bare.md"
    f.write_text("just some text\nwith two lines", encoding="utf-8")
    meta, body = _parse_doc(f)
    assert meta["source_type"] == "unknown"
    assert "just some text" in body
