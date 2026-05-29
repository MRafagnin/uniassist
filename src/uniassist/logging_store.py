"""SQLite-backed query log — Phase 3."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from uniassist.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (datetime('now')),
    endpoint TEXT NOT NULL,
    input_redacted TEXT NOT NULL,
    retrieved_ids TEXT,
    answer TEXT,
    latency_ms INTEGER,
    tokens_in INTEGER,
    tokens_out INTEGER,
    model TEXT
);
"""


@contextmanager
def connect(path: Path | None = None):
    path = path or settings.sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()
