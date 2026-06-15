"""Filename-pattern → rubric-name registry."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Pattern list – evaluated in order; first match wins.
# Each tuple is (compiled_pattern, rubric_name).
# ---------------------------------------------------------------------------
RUBRIC_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Exact filenames
    (re.compile(r"^final_summary\.json$"), "final_summary"),
    (re.compile(r"^full_summary\.json$"), "final_summary"),
    (re.compile(r"^split_document_summaries\.json$"), "document_summaries"),
    (re.compile(r"^findings\.json$"), "extraction_list"),
    (re.compile(r"^surgeries\.json$"), "extraction_list"),
    (re.compile(r"^sick_permits\.json$"), "extraction_list"),
    (re.compile(r"^incidents\.json$"), "extraction_list"),
    (re.compile(r"^disabilities\.json$"), "extraction_list"),
    (re.compile(r"^adl_records\.json$"), "extraction_list"),
    (re.compile(r"^accident_details\.json$"), "extraction_list"),
    (re.compile(r"^clean_medications\.json$"), "extraction_list"),
    (re.compile(r"^filter_diagnoses\.json$"), "grouping_boundary"),
    (re.compile(r"^merge_diagnoses\.json$"), "grouping_boundary"),
    (re.compile(r"^personal_details\.json$"), "personal_committee"),
    (re.compile(r"^past_committees\.json$"), "personal_committee"),
    # Parameterised patterns
    (re.compile(r"^Page\d+<>Page\d+\.json$"), "grouping_boundary"),
    (re.compile(r"^medical_doc_\d+\.json$"), "document_summaries"),
    (re.compile(r"^document_conditions_classifier_\d+\.json$"), "classifier"),
    (re.compile(r"^diagnoses_by_date_classifier_\d+\.json$"), "classifier"),
    (re.compile(r"^medical_doc_validator_\d+\.json$"), "classifier"),
    (re.compile(r"^check_duplication_\d+<>\d+\.json$"), "duplicate_check"),
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
