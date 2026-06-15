"""Evaluate a single parsed turn using a rubric, golden examples, and an LLM."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from llm_judge.config import Settings
from llm_judge.llm_client import LLMClient
from llm_judge.models import ParsedTurn, Verdict

logger = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")


def _strip_fences(text: str) -> str:
    """Remove markdown code fences around JSON if present."""
    m = _CODE_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _parse_verdict_json(text: str) -> dict:
    """Parse LLM response text into a verdict dict. Raises ValueError on failure."""
    cleaned = _strip_fences(text)
    data = json.loads(cleaned)
    for key in ("score", "per_criterion", "flagged", "reasoning"):
        if key not in data:
            raise ValueError(f"Missing required key {key!r} in verdict JSON")
    return data


def _truncate_input(
    parsed_turn: ParsedTurn, config: Settings
) -> str:
    """Return (possibly truncated) input string.

    For duplicate_check schema: parse the combined JSON and truncate each
    sub-field to ``JUDGE_INPUT_TRUNCATE_CHARS // 2`` chars symmetrically.
    For all other schemas: truncate the raw input string to
    ``JUDGE_INPUT_TRUNCATE_CHARS`` chars.

    A WARNING is logged whenever truncation actually occurs.
    Never truncates the output field.
    """
    limit = config.judge_input_truncate_chars

    if parsed_turn.schema_variant == "duplicate_check":
        half = limit // 2
        try:
            combined = json.loads(parsed_turn.input)
        except json.JSONDecodeError:
            combined = {"input1": parsed_turn.input, "input2": ""}

        input1 = combined.get("input1", "")
        input2 = combined.get("input2", "")

        # Normalise to string for truncation
        input1_str = input1 if isinstance(input1, str) else json.dumps(input1)
        input2_str = input2 if isinstance(input2, str) else json.dumps(input2)

        truncated = False
        if len(input1_str) > half:
            input1_str = input1_str[:half]
            truncated = True
        if len(input2_str) > half:
            input2_str = input2_str[:half]
            truncated = True

        if truncated:
            logger.warning(
                "Truncating duplicate_check inputs for %s/%s",
                parsed_turn.case_id,
                parsed_turn.filename,
            )
        return json.dumps({"input1": input1_str, "input2": input2_str})

    # All other schemas
    raw = parsed_turn.input
    if len(raw) > limit:
        logger.warning(
            "Truncating input for %s/%s (original_len=%d, limit=%d)",
            parsed_turn.case_id,
            parsed_turn.filename,
            len(raw),
            limit,
        )
        return raw[:limit]
    return raw


def _build_system_prompt(
    rubric_content: str,
    golden_examples: list[dict],
    config: Settings,
) -> str:
    """Assemble the full system prompt."""
    parts = [
        rubric_content.strip(),
        "",
        f"JUDGE_SCORE_THRESHOLD: {config.judge_score_threshold}",
    ]

    if golden_examples:
        parts.append("")
        parts.append("## Golden Examples (high-quality outputs to calibrate your scoring)")
        parts.append("")
        for i, example in enumerate(golden_examples, start=1):
            parts.append(f"### Golden Example {i}")
            parts.append(json.dumps(example, indent=2, default=str))
            parts.append("")

    return "\n".join(parts)


def _build_user_message(parsed_turn: ParsedTurn, effective_input: str) -> str:
    """Format the turn fields as a user message for the judge."""
    output = parsed_turn.output
    if isinstance(output, dict):
        output_str = json.dumps(output, indent=2, default=str)
    else:
        output_str = str(output)

    lines = [
        f"schema_variant: {parsed_turn.schema_variant}",
        f"prompt: {parsed_turn.prompt}",
        f"input: {effective_input}",
        f"output: {output_str}",
    ]
    return "\n".join(lines)


def evaluate_turn(
    parsed_turn: ParsedTurn,
    rubric_content: str,
    golden_examples: list[dict],
    llm_client: LLMClient,
    config: Settings,
    prompt_type: str = "",
) -> Verdict:
    """Evaluate one turn and return a Verdict.

    Retry once on parse failure. If the second attempt also fails, return a
    Verdict with ``parse_error=True``.
    """
    effective_input = _truncate_input(parsed_turn, config)
    system_prompt = _build_system_prompt(rubric_content, golden_examples, config)
    user_msg = _build_user_message(parsed_turn, effective_input)

    now = datetime.now(tz=timezone.utc)

    # First attempt
    raw_response: str = ""
    try:
        raw_response = llm_client.judge(system=system_prompt, user=user_msg)
        data = _parse_verdict_json(raw_response)
    except Exception as first_exc:
        logger.warning(
            "First parse attempt failed for %s/%s: %s – retrying",
            parsed_turn.case_id,
            parsed_turn.filename,
            first_exc,
        )
        retry_msg = (
            "Your previous response was not valid JSON. "
            "Respond ONLY with the JSON object, no other text.\n\n"
            + user_msg
        )
        try:
            raw_response = llm_client.judge(system=system_prompt, user=retry_msg)
            data = _parse_verdict_json(raw_response)
        except Exception as second_exc:
            logger.error(
                "Second parse attempt also failed for %s/%s: %s",
                parsed_turn.case_id,
                parsed_turn.filename,
                second_exc,
            )
            return Verdict(
                case_id=parsed_turn.case_id,
                filename=parsed_turn.filename,
                prompt_type=prompt_type,
                schema_variant=parsed_turn.schema_variant,
                score=None,
                per_criterion={},
                flagged=False,
                reasoning="",
                parse_error=True,
                raw_response=raw_response[:500] if raw_response else None,
                evaluated_at=now,
            )

    return Verdict(
        case_id=parsed_turn.case_id,
        filename=parsed_turn.filename,
        prompt_type=prompt_type,
        schema_variant=parsed_turn.schema_variant,
        score=int(data["score"]),
        per_criterion=data.get("per_criterion", {}),
        flagged=bool(data["flagged"]),
        reasoning=str(data.get("reasoning", "")),
        parse_error=False,
        raw_response=None,
        evaluated_at=now,
    )
