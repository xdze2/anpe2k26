"""Shared types for the enrichment pipeline."""

from __future__ import annotations

from pydantic import BaseModel


class FetchTarget(BaseModel):
    tool: str
    target: str


class SummarizeResult(BaseModel):
    status: str  # "ok" | "not_relevant" | "no_data"
    summary: str = ""
    new_targets: list[FetchTarget] = []
    prompt: str = ""
    version: str = ""
    model: str = ""
