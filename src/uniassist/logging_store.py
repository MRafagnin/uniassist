"""SQLite-backed query log for /chat and /triage calls."""
from __future__ import annotations

import json
import sqlite3
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uniassist.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    input_redacted TEXT NOT NULL,
    retrieved_ids TEXT,
    answer TEXT,
    latency_ms INTEGER,
    tokens_in INTEGER,
    tokens_out INTEGER,
    model TEXT
);
CREATE INDEX IF NOT EXISTS idx_queries_endpoint ON queries(endpoint);
CREATE INDEX IF NOT EXISTS idx_queries_ts ON queries(ts);
"""

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_conn_path: Path | None = None


def _get_conn(path: Path | None = None) -> sqlite3.Connection:
    global _conn, _conn_path
    with _lock:
        if path is None:
            path = _conn_path or settings.sqlite_path
        if _conn is None or _conn_path != path:
            if _conn is not None:
                _conn.close()
            path.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(path), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(SCHEMA)
            _conn.commit()
            _conn_path = path
        return _conn


def init_db(path: Path | None = None) -> None:
    """Create schema if needed. Idempotent."""
    _get_conn(path)


def reset_for_tests(path: Path | None = None) -> None:
    """Force-close and reopen the cached connection. Tests use this with a temp path."""
    global _conn, _conn_path
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
        _conn_path = None
    if path is not None:
        _get_conn(path)


def log_query(
    *,
    endpoint: str,
    input_redacted: str,
    retrieved_ids: list[str] | None = None,
    answer: str | None = None,
    latency_ms: int | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    model: str | None = None,
) -> int:
    conn = _get_conn()
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    with _lock:
        cur = conn.execute(
            "INSERT INTO queries (ts, endpoint, input_redacted, retrieved_ids, answer,"
            " latency_ms, tokens_in, tokens_out, model)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                endpoint,
                input_redacted,
                json.dumps(retrieved_ids or []),
                answer,
                latency_ms,
                tokens_in,
                tokens_out,
                model,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def recent(n: int = 50) -> list[dict[str, Any]]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT * FROM queries ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in rows]


def summary() -> dict[str, Any]:
    """Per-endpoint counts, P50/P95 latency, and top triage categories."""
    conn = _get_conn()
    with _lock:
        counts = {
            r["endpoint"]: r["c"]
            for r in conn.execute(
                "SELECT endpoint, COUNT(*) AS c FROM queries GROUP BY endpoint"
            ).fetchall()
        }
        latencies: dict[str, dict[str, float | None]] = {}
        for endpoint in counts:
            vals = [
                r["latency_ms"]
                for r in conn.execute(
                    "SELECT latency_ms FROM queries WHERE endpoint = ?"
                    " AND latency_ms IS NOT NULL ORDER BY latency_ms",
                    (endpoint,),
                ).fetchall()
            ]
            latencies[endpoint] = {
                "p50": _percentile(vals, 50),
                "p95": _percentile(vals, 95),
                "n": len(vals),
            }
        triage_answers = [
            r["answer"]
            for r in conn.execute(
                "SELECT answer FROM queries WHERE endpoint = 'triage' AND answer IS NOT NULL"
            ).fetchall()
        ]
    categories: Counter[str] = Counter()
    for raw in triage_answers:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        cat = data.get("category") if isinstance(data, dict) else None
        if cat:
            categories[cat] += 1
    return {
        "counts": counts,
        "latency_ms": latencies,
        "top_categories": categories.most_common(5),
    }


def _percentile(values: list[int], pct: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    k = (len(values) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return float(values[f])
    return values[f] + (values[c] - values[f]) * (k - f)
