from uniassist.ingest.servicenow_scraper import (
    KB_ARTICLE_RE,
    _is_servicenow,
    _slug_for,
)


def test_kb_article_regex_matches():
    url = "https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=abc123"
    assert KB_ARTICLE_RE.search(url)


def test_kb_article_regex_ignores_topic():
    url = "https://sydneyuni.service-now.com/sm?id=usyd_emp_taxonomy_topic&topic_id=xyz"
    assert KB_ARTICLE_RE.search(url) is None


def test_is_servicenow_host():
    assert _is_servicenow("https://sydneyuni.service-now.com/sm?id=foo")
    assert not _is_servicenow("https://www.sydney.edu.au/students/student-it.html")


def test_slug_for_includes_kb_id():
    url = "https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=b6022d07c36b79500b2b329f05013174"
    slug = _slug_for(url)
    assert slug.startswith("sn-b6022d07c36b79500b2b329f")
    assert len(slug.rsplit("-", 1)[-1]) == 10  # short sha


def test_slug_for_stable():
    url = "https://sydneyuni.service-now.com/sm?id=kb_article_view&sys_kb_id=abc"
    assert _slug_for(url) == _slug_for(url)
