from pathlib import Path

from uniassist.ingest import manual_loader

SERVICENOW_HTML = """
<html>
  <head>
    <title>How to reset your UniKey password</title>
    <link rel="canonical" href="https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=abc123">
  </head>
  <body>
    <nav>ServiceNow chrome here</nav>
    <main>
      <h1>How to reset your UniKey password</h1>
      <p>If you have forgotten your UniKey password, you can reset it online.</p>
      <ol>
        <li>Go to the identity portal.</li>
        <li>Click "Forgot password".</li>
        <li>Answer your security questions.</li>
        <li>Choose a new password that meets the complexity rules.</li>
      </ol>
      <p>If you remain locked out, contact the ICT Service Desk.</p>
    </main>
    <footer>ServiceNow footer</footer>
  </body>
</html>
"""


def test_load_one_html(tmp_path: Path):
    f = tmp_path / "kb-password.html"
    f.write_text(SERVICENOW_HTML, encoding="utf-8")
    doc = manual_loader.load_one(f)
    assert doc is not None
    assert doc.source_type == "servicenow_kb"
    assert doc.source_url == "https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=abc123"
    assert "reset" in doc.body_markdown.lower()
    assert "servicenow chrome" not in doc.body_markdown.lower()


def test_load_one_markdown_passthrough(tmp_path: Path):
    f = tmp_path / "kb-vpn.md"
    f.write_text(
        "---\n"
        "source_url: https://example.test/vpn\n"
        'title: "VPN setup"\n'
        "---\n\n"
        "# VPN setup\n\n"
        + ("To connect to the university VPN, follow these steps. " * 20),
        encoding="utf-8",
    )
    doc = manual_loader.load_one(f)
    assert doc is not None
    assert doc.source_url == "https://example.test/vpn"
    assert doc.title == "VPN setup"
    assert doc.source_type == "servicenow_kb"


def test_load_one_skips_thin_doc(tmp_path: Path):
    f = tmp_path / "tiny.html"
    f.write_text("<html><body><p>too short</p></body></html>", encoding="utf-8")
    assert manual_loader.load_one(f) is None
