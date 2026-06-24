"""Pydantic models and named tuples for the LLM Judge service."""

from __future__ import annotations

from collections import namedtuple
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# BlobMeta – lightweight metadata for a GCS blob
# ---------------------------------------------------------------------------
BlobMeta = namedtuple("BlobMeta", ["case_id", "filename", "modified_time"])
# case_id: str
# filename: str
# modified_time: datetime | None


# ---------------------------------------------------------------------------
# ParsedTurn – normalised view of one log entry
# ---------------------------------------------------------------------------
class ParsedTurn(BaseModel):
    prompt: str
    input: str
    output: Any  # str or dict depending on schema_variant
    schema_variant: str  # 'standard' | 'tool_use' | 'boundary_check' | 'duplicate_check'
    case_id: str
    filename: str


# ---------------------------------------------------------------------------
# Verdict – result of evaluating one turn
# ---------------------------------------------------------------------------
class Verdict(BaseModel):
    case_id: str
    filename: str
    prompt_type: str  # rubric name (e.g. 'full_summary')
    schema_variant: str
    score: Optional[int] = None
    per_criterion: dict[str, Any] = Field(default_factory=dict)
    flagged: bool = False
    reasoning: str = ""
    parse_error: bool = False
    raw_response: Optional[str] = None
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    run_id: str = ""  # stamped at run time; empty for older verdicts


# ---------------------------------------------------------------------------
# FlaggedItem – summary entry for a single flagged turn in the digest
# ---------------------------------------------------------------------------
class FlaggedItem(BaseModel):
    case_id: str
    filename: str
    prompt_type: str
    score: Optional[int] = None
    reasoning_snippet: str


# ---------------------------------------------------------------------------
# RunSummary – aggregate result of one batch run
# ---------------------------------------------------------------------------
class RunSummary(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime
    case_id: Optional[str] = None
    total_logs: int = 0
    evaluated: int = 0
    skipped_existing: int = 0
    unmapped: int = 0
    flagged: int = 0
    errors: int = 0
    parse_errors: int = 0
    by_prompt_type: dict[str, int] = Field(default_factory=dict)
    flagged_items: list[FlaggedItem] = Field(default_factory=list)
