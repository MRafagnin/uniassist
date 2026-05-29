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


# Crude keyword heuristic — enough for Phase 1; refined in Phase 2 with an LLM call.
IN_SCOPE_KEYWORDS = (
    "wifi", "wi-fi", "uniwifi", "eduroam", "vpn", "password", "account",
    "email", "outlook", "m365", "office 365", "microsoft 365", "canvas",
    "lms", "printer", "printing", "software", "license", "licence",
    "mfa", "multi-factor", "okta", "laptop", "loan", "usyd", "sydney",
    "student", "staff", "ict", "service desk", "it",
)


def is_likely_in_scope(text: str) -> bool:
    """True if the text mentions at least one in-scope keyword."""
    lowered = text.lower()
    return any(kw in lowered for kw in IN_SCOPE_KEYWORDS)
