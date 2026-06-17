"""Load golden examples for a given prompt type from storage."""

from __future__ import annotations

import logging

from llm_judge.storage.client import StorageClient

logger = logging.getLogger(__name__)


def load_golden_examples(storage_client: StorageClient, prompt_type: str) -> list[dict]:
    """Return up to 2 golden example dicts for *prompt_type*.

    Reads from ``{GOLDEN_BUCKET}/{GOLDEN_PREFIX}{prompt_type}/``.
    Returns an empty list when no golden examples exist for the type.

    Golden JSONs must contain an ``"expected_verdict": "pass"`` field,
    indicating they are positive (high-quality) examples.
    """
    examples = storage_client.read_golden_examples(prompt_type)
    if not examples:
        logger.info("No golden examples found for prompt_type=%s", prompt_type)
        return []
    # Defensive: cap at 2 (StorageClient already caps, but be safe)
    capped = examples[:2]
    logger.info(
        "Loaded %d golden example(s) for prompt_type=%s", len(capped), prompt_type
    )
    return capped
