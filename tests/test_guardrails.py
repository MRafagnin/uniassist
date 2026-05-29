from uniassist.guardrails import is_in_scope, is_likely_in_scope, redact, redact_pii


def test_redacts_email():
    assert redact_pii("contact me at jane.doe@sydney.edu.au please") == (
        "contact me at [REDACTED_EMAIL] please"
    )


def test_redacts_student_id():
    assert redact_pii("my SID is 510123456 thanks") == "my SID is [REDACTED_ID] thanks"


def test_does_not_redact_short_or_long_numbers():
    assert "12345" in redact_pii("ticket 12345 was raised")
    assert "1234567890" in redact_pii("ref 1234567890 here")


def test_redacts_both_in_one_string():
    out = redact_pii("510123456 and a@b.co")
    assert "[REDACTED_ID]" in out
    assert "[REDACTED_EMAIL]" in out


def test_in_scope_detection():
    assert is_likely_in_scope("How do I connect to UniWiFi on my laptop?")
    assert is_likely_in_scope("Canvas won't load")
    assert not is_likely_in_scope("What's the weather like today?")


def test_redact_alias():
    assert redact("a@b.co") == redact_pii("a@b.co")


def test_is_in_scope_keywords_and_verbs():
    assert is_in_scope("How do I reset my password?")
    assert is_in_scope("install Adobe Acrobat")
    assert is_in_scope("connect to eduroam")
    assert not is_in_scope("Recommend a recipe for risotto")
