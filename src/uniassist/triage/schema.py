"""Pydantic schema for the structured-output triage chain."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "WiFi",
    "Email/M365",
    "VPN",
    "Account/Password",
    "LMS/Canvas",
    "Hardware",
    "Software-licensing",
    "Other",
]

Priority = Literal["P1", "P2", "P3", "P4"]


class TriageResult(BaseModel):
    category: Category
    subcategory: str = Field(..., description="Short free-text refinement, e.g. 'eduroam connection'")
    priority: Priority
    suggested_queue: str = Field(..., description="Team queue, e.g. 'ICT-Network', 'ICT-Identity'")
    rationale: str = Field(..., description="One-sentence justification for the classification.")
    confidence: float = Field(..., ge=0.0, le=1.0)
