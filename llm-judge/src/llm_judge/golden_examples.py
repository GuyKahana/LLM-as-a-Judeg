"""Load golden examples for a given prompt type from storage."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from llm_judge.storage.client import StorageClient

logger = logging.getLogger(__name__)

# Bundled fallback goldens shipped with the package. Used only when the
# golden bucket has no examples for a given prompt type.
_BUNDLED_GOLDEN_DIR = Path(__file__).parent / "rubrics" / "golden"


def _load_bundled_examples(prompt_type: str, limit: int) -> list[dict]:
    """Return up to *limit* golden examples from the in-repo fallback directory."""
    rubric_dir = _BUNDLED_GOLDEN_DIR / prompt_type
    if not rubric_dir.is_dir():
        return []

    examples: list[dict] = []
    for path in sorted(rubric_dir.glob("*.json"))[:limit]:
        try:
            examples.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("Failed to read bundled golden example %s: %s", path, exc)
    return examples


def load_golden_examples(
    storage_client: StorageClient,
    prompt_type: str,
    limit: int = 2,
) -> list[dict]:
    """Return up to *limit* golden example dicts for *prompt_type*.

    Lookup order:
    1. ``{GOLDEN_BUCKET}/{GOLDEN_PREFIX}{prompt_type}/`` via the storage client.
    2. Fallback: bundled examples in ``src/llm_judge/rubrics/golden/{prompt_type}/``
       — used only when the bucket returns zero examples.

    Returns an empty list when neither source has examples for the type.

    Golden JSONs must contain an ``"expected_verdict": "pass"`` field,
    indicating they are positive (high-quality) examples.
    """
    examples = storage_client.read_golden_examples(prompt_type)
    source = "bucket"
    if not examples:
        examples = _load_bundled_examples(prompt_type, limit)
        source = "bundled"

    capped = examples[:limit]
    actual = len(capped)

    if actual < limit:
        logger.warning(
            "Configured JUDGE_GOLDEN_EXAMPLES_MAX=%d but only %d golden example(s) "
            "available for prompt_type=%s (source=%s) — running with %d.",
            limit, actual, prompt_type, source if actual else "none", actual,
        )
    else:
        logger.info(
            "Loaded %d golden example(s) for prompt_type=%s (source=%s)",
            actual, prompt_type, source,
        )
    return capped
