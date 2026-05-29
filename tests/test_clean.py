from uniassist.ingest.clean import html_to_markdown

SAMPLE_HTML = """
<html>
  <head><title>Connect to UniWiFi</title></head>
  <body>
    <nav>Top nav noise here that should be stripped</nav>
    <header>Header noise</header>
    <main>
      <h1>Connect to UniWiFi</h1>
      <p>Follow these steps to connect your device.</p>
      <h2>On Windows</h2>
      <ol><li>Open settings</li><li>Pick UniWiFi</li></ol>
    </main>
    <footer>Footer noise</footer>
    <script>var x = 1;</script>
  </body>
</html>
"""


def test_extracts_title():
    title, _ = html_to_markdown(SAMPLE_HTML)
    assert title == "Connect to UniWiFi"


def test_strips_nav_footer_script():
    _, body = html_to_markdown(SAMPLE_HTML)
    lowered = body.lower()
    assert "nav noise" not in lowered
    assert "footer noise" not in lowered
    assert "var x" not in lowered


def test_preserves_main_body():
    _, body = html_to_markdown(SAMPLE_HTML)
    assert "Follow these steps" in body
    assert "On Windows" in body
    assert "Pick UniWiFi" in body
