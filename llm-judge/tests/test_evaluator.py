"""Tests for evaluator.evaluate_turn."""

from __future__ import annotations

import json

import pytest

from llm_judge.evaluator import evaluate_turn
from llm_judge.models import ParsedTurn


def _make_turn(
    schema_variant: str = "standard",
    prompt: str = "Summarize.",
    input_text: str = "Patient history.",
    output: str = "Summary.",
    case_id: str = "case-001",
    filename: str = "final_summary.json",
) -> ParsedTurn:
    return ParsedTurn(
        prompt=prompt,
        input=input_text,
        output=output,
        schema_variant=schema_variant,
        case_id=case_id,
        filename=filename,
    )


RUBRIC_CONTENT = "You are a judge.\n\n## Required Output Format\nRespond only with JSON."
GOLDEN_EXAMPLES = []


class TestCleanResponseParsing:
    def test_returns_verdict_with_correct_fields(self, mock_llm_client, config):
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert verdict.score == 4
        assert verdict.flagged is False
        assert verdict.parse_error is False
        assert verdict.reasoning == "The output is good."

    def test_strips_json_code_fence(self, mock_llm_client, config):
        mock_llm_client.judge.return_value = (
            "```json\n"
            + json.dumps({"score": 5, "per_criterion": {}, "flagged": False, "reasoning": "Great"})
            + "\n```"
        )
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert verdict.score == 5
        assert verdict.parse_error is False

    def test_strips_plain_code_fence(self, mock_llm_client, config):
        mock_llm_client.judge.return_value = (
            "```\n"
            + json.dumps({"score": 3, "per_criterion": {}, "flagged": True, "reasoning": "Bad"})
            + "\n```"
        )
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert verdict.score == 3
        assert verdict.flagged is True

    def test_per_criterion_preserved(self, mock_llm_client, config):
        mock_llm_client.judge.return_value = json.dumps({
            "score": 4,
            "per_criterion": {"completeness": 4, "accuracy": 4},
            "flagged": False,
            "reasoning": "Good output.",
        })
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert verdict.per_criterion == {"completeness": 4, "accuracy": 4}


class TestRetryAndParseError:
    def test_malformed_json_triggers_retry(self, mock_llm_client, config):
        """First response is invalid JSON, second is valid."""
        valid_response = json.dumps({
            "score": 3,
            "per_criterion": {},
            "flagged": True,
            "reasoning": "Retry succeeded",
        })
        mock_llm_client.judge.side_effect = ["NOT VALID JSON{{", valid_response]
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert mock_llm_client.judge.call_count == 2
        assert verdict.parse_error is False
        assert verdict.score == 3

    def test_second_failure_returns_parse_error_verdict(self, mock_llm_client, config):
        """Both responses invalid → parse_error=True, flagged=False."""
        mock_llm_client.judge.side_effect = ["BAD JSON", "ALSO BAD JSON"]
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert verdict.parse_error is True
        assert verdict.flagged is False
        assert verdict.score is None

    def test_parse_error_raw_response_truncated_to_500(self, mock_llm_client, config):
        long_bad = "X" * 1000
        mock_llm_client.judge.side_effect = [long_bad, long_bad]
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert verdict.parse_error is True
        assert verdict.raw_response is not None
        assert len(verdict.raw_response) <= 500

    def test_missing_key_triggers_retry(self, mock_llm_client, config):
        """Response missing 'score' key counts as parse failure."""
        valid = json.dumps({
            "score": 5,
            "per_criterion": {},
            "flagged": False,
            "reasoning": "ok",
        })
        mock_llm_client.judge.side_effect = [
            json.dumps({"per_criterion": {}, "flagged": False, "reasoning": "no score"}),
            valid,
        ]
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert verdict.score == 5
        assert verdict.parse_error is False

    def test_null_score_triggers_retry(self, mock_llm_client, config):
        """A null score counts as a parse failure and triggers the retry."""
        valid = json.dumps({
            "score": 4,
            "per_criterion": {},
            "flagged": False,
            "reasoning": "ok",
        })
        mock_llm_client.judge.side_effect = [
            json.dumps({"score": None, "per_criterion": {}, "flagged": False, "reasoning": "unsure"}),
            valid,
        ]
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert mock_llm_client.judge.call_count == 2
        assert verdict.score == 4
        assert verdict.parse_error is False

    def test_non_numeric_score_both_attempts_returns_parse_error(self, mock_llm_client, config):
        """A non-numeric score on both attempts → parse_error, never a hard error."""
        bad = json.dumps({"score": "high", "per_criterion": {}, "flagged": False, "reasoning": "x"})
        mock_llm_client.judge.side_effect = [bad, bad]
        turn = _make_turn()
        verdict = evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        assert verdict.parse_error is True
        assert verdict.score is None


class TestTruncation:
    def test_long_input_truncated_for_standard(self, mock_llm_client, config):
        config.judge_input_truncate_chars = 50
        long_input = "A" * 200
        turn = _make_turn(input_text=long_input)
        evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        call_args = mock_llm_client.judge.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        # The input in the user message should be 50 chars, not 200
        assert "A" * 200 not in user_msg
        assert "A" * 50 in user_msg

    def test_short_input_not_truncated(self, mock_llm_client, config):
        config.judge_input_truncate_chars = 1000
        turn = _make_turn(input_text="short input")
        evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        call_args = mock_llm_client.judge.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        assert "short input" in user_msg

    def test_output_never_truncated(self, mock_llm_client, config):
        config.judge_input_truncate_chars = 10
        long_output = "O" * 5000
        turn = _make_turn(input_text="x", output=long_output)
        evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "final_summary")
        call_args = mock_llm_client.judge.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        assert "O" * 5000 in user_msg


class TestDuplicateCheckTruncation:
    def test_both_inputs_truncated_symmetrically(self, mock_llm_client, config):
        config.judge_input_truncate_chars = 100  # 50 chars per side
        input_data = json.dumps({
            "input1": "A" * 200,
            "input2": "B" * 200,
        })
        turn = _make_turn(
            schema_variant="duplicate_check",
            input_text=input_data,
            filename="check_duplication_1<>2.json",
        )
        evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "duplicate_check")
        call_args = mock_llm_client.judge.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        # Neither full 200-char string should appear
        assert "A" * 200 not in user_msg
        assert "B" * 200 not in user_msg
        # But truncated versions should
        assert "A" * 50 in user_msg
        assert "B" * 50 in user_msg

    def test_short_duplicate_inputs_not_truncated(self, mock_llm_client, config):
        config.judge_input_truncate_chars = 10000
        input_data = json.dumps({"input1": "short A", "input2": "short B"})
        turn = _make_turn(
            schema_variant="duplicate_check",
            input_text=input_data,
            filename="check_duplication_1<>2.json",
        )
        evaluate_turn(turn, RUBRIC_CONTENT, GOLDEN_EXAMPLES, mock_llm_client, config, "duplicate_check")
        call_args = mock_llm_client.judge.call_args
        user_msg = call_args[1]["user"] if "user" in call_args[1] else call_args[0][1]
        assert "short A" in user_msg
        assert "short B" in user_msg
