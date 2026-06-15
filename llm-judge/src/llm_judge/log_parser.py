"""Parse raw log JSON into a normalised ParsedTurn."""

from __future__ import annotations

import json
import logging

from llm_judge.models import ParsedTurn

logger = logging.getLogger(__name__)


def parse_log(raw_json: dict, filename: str, case_id: str) -> ParsedTurn:
    """Detect schema variant and return a normalised ParsedTurn.

    Schema detection priority:
    1. Has ``input1`` AND ``input2`` keys          → ``duplicate_check``
    2. Has ``prompt`` AND ``output`` is a dict     → ``tool_use``
    3. Has ``prompt``                              → ``standard``
    4. Anything else                               → ``boundary_check``
    """
    if "input1" in raw_json and "input2" in raw_json:
        # Duplicate-check schema
        combined_input = json.dumps(
            {"input1": raw_json["input1"], "input2": raw_json["input2"]}
        )
        return ParsedTurn(
            prompt="[duplicate check — comparing two inputs]",
            input=combined_input,
            output=raw_json.get("output", ""),
            schema_variant="duplicate_check",
            case_id=case_id,
            filename=filename,
        )

    if "prompt" in raw_json and isinstance(raw_json.get("output"), dict):
        # Tool-use schema
        return ParsedTurn(
            prompt=raw_json["prompt"],
            input=raw_json.get("input", ""),
            output=raw_json["output"],
            schema_variant="tool_use",
            case_id=case_id,
            filename=filename,
        )

    if "prompt" in raw_json:
        # Standard schema
        return ParsedTurn(
            prompt=raw_json["prompt"],
            input=raw_json.get("input", ""),
            output=raw_json.get("output", ""),
            schema_variant="standard",
            case_id=case_id,
            filename=filename,
        )

    # Boundary-check schema
    return ParsedTurn(
        prompt="[boundary check — no separate prompt logged]",
        input=raw_json.get("input", ""),
        output=raw_json.get("output", ""),
        schema_variant="boundary_check",
        case_id=case_id,
        filename=filename,
    )
