"""FastAPI app — stub until Phase 2 wires up the chains."""
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="UniAssist", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
