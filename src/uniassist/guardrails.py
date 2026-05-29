"""PII redaction + out-of-scope refusal helpers."""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# USYD student/staff IDs are 9 digits (e.g. 510123456). Avoid matching inside longer numbers.
SID_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")


def redact_pii(text: str) -> str:
    """Replace emails and 9-digit IDs with stable placeholders. Safe for logging."""
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = SID_RE.sub("[REDACTED_ID]", text)
    return text


# Alias used by Phase 2 callers.
redact = redact_pii


IN_SCOPE_KEYWORDS = (
    "wifi", "wi-fi", "uniwifi", "eduroam", "vpn", "password", "account",
    "email", "outlook", "m365", "office 365", "microsoft 365", "canvas",
    "lms", "printer", "printing", "print", "scan", "copy", "software",
    "license", "licence", "adobe", "zoom", "qualtrics", "mfa", "multi-factor",
    "okta", "sso", "unikey", "servicenow", "laptop", "mac", "macbook",
    "windows", "library", "loan", "usyd", "sydney", "student", "staff",
    "ict", "service desk", "it",
)

IN_SCOPE_VERBS = (
    "install", "connect", "configure", "log in", "login", "sign in", "signin",
    "access", "set up", "setup", "reset", "update", "enrol", "enroll",
    "activate", "forward",
)


def is_in_scope(question: str) -> bool:
    """Soft heuristic: True if the question looks like an IT support topic."""
    lowered = question.lower()
    if any(kw in lowered for kw in IN_SCOPE_KEYWORDS):
        return True
    return any(v in lowered for v in IN_SCOPE_VERBS)


def is_likely_in_scope(text: str) -> bool:
    """Back-compat alias used by Phase 1 tests."""
    return is_in_scope(text)
