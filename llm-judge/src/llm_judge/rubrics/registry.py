"""Filename-pattern → rubric-name registry."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Pattern list – evaluated in order; first match wins.
# Each tuple is (compiled_pattern, rubric_name).
# Every distinct filename type has its own rubric (and prompt file).
# Parameterised patterns share one rubric across their numeric variants.
# ---------------------------------------------------------------------------
RUBRIC_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Exact filenames
    (re.compile(r"^full_summary\.json$"), "full_summary"),
    (re.compile(r"^split_document_summaries\.json$"), "split_document_summaries_by_dates"),
    (re.compile(r"^sick_permits\.json$"), "sick_permits"),
    (re.compile(r"^personal_details\.json$"), "personal_details"),
    (re.compile(r"^past_committees\.json$"), "past_committees"),
    # Parameterised patterns
    (re.compile(r"^Page\d+<>Page\d+\.json$"), "same_document"),
    (re.compile(r"^medical_doc_\d+\.json$"), "medical_document"),
    (re.compile(r"^medical_doc_validator_\d+\.json$"), "medical_document_validator"),
    (re.compile(r"^check_duplication_\d+<>\d+\.json$"), "document_duplicate_check"),
]

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def get_rubric_name(filename: str) -> Optional[str]:
    """Return the rubric name for *filename*, or None if unmapped."""
    for pattern, name in RUBRIC_PATTERNS:
        if pattern.match(filename):
            return name
    return None


def get_rubric_content(rubric_name: str) -> str:
    """Load and return the markdown prompt for *rubric_name*.

    Raises FileNotFoundError if the prompt file does not exist.
    """
    prompt_path = _PROMPTS_DIR / f"{rubric_name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Rubric prompt file not found: {prompt_path}. "
            f"Expected rubric name: {rubric_name!r}"
        )
    return prompt_path.read_text(encoding="utf-8")


def list_rubrics() -> list[tuple[str, str]]:
    """Return all (pattern_string, rubric_name) pairs for display."""
    return [(p.pattern, name) for p, name in RUBRIC_PATTERNS]
