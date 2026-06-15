"""Tests for log_parser.parse_log."""

from __future__ import annotations

import json

import pytest

from llm_judge.log_parser import parse_log


class TestStandardSchema:
    def test_schema_variant(self, standard_log):
        result = parse_log(standard_log, "final_summary.json", "case-001")
        assert result.schema_variant == "standard"

    def test_prompt_preserved(self, standard_log):
        result = parse_log(standard_log, "final_summary.json", "case-001")
        assert result.prompt == "Summarize this."

    def test_input_preserved(self, standard_log):
        result = parse_log(standard_log, "final_summary.json", "case-001")
        assert "hypertension" in result.input

    def test_output_is_string(self, standard_log):
        result = parse_log(standard_log, "final_summary.json", "case-001")
        assert isinstance(result.output, str)

    def test_case_id_and_filename(self, standard_log):
        result = parse_log(standard_log, "final_summary.json", "case-001")
        assert result.case_id == "case-001"
        assert result.filename == "final_summary.json"


class TestToolUseSchema:
    def test_schema_variant(self, tool_use_log):
        result = parse_log(tool_use_log, "findings.json", "case-002")
        assert result.schema_variant == "tool_use"

    def test_output_is_dict(self, tool_use_log):
        result = parse_log(tool_use_log, "findings.json", "case-002")
        assert isinstance(result.output, dict)
        assert "findings" in result.output

    def test_prompt_preserved(self, tool_use_log):
        result = parse_log(tool_use_log, "findings.json", "case-002")
        assert result.prompt == "Extract findings."


class TestBoundaryCheckSchema:
    def test_schema_variant(self, boundary_check_log):
        result = parse_log(boundary_check_log, "Page1<>Page2.json", "case-003")
        assert result.schema_variant == "boundary_check"

    def test_synthesized_prompt(self, boundary_check_log):
        result = parse_log(boundary_check_log, "Page1<>Page2.json", "case-003")
        assert result.prompt == "[boundary check — no separate prompt logged]"

    def test_output_preserved(self, boundary_check_log):
        result = parse_log(boundary_check_log, "Page1<>Page2.json", "case-003")
        assert result.output == "yes"

    def test_input_preserved(self, boundary_check_log):
        result = parse_log(boundary_check_log, "Page1<>Page2.json", "case-003")
        assert result.input == "Is this relevant?"


class TestDuplicateCheckSchema:
    def test_schema_variant(self, duplicate_check_log):
        result = parse_log(duplicate_check_log, "check_duplication_1<>2.json", "case-004")
        assert result.schema_variant == "duplicate_check"

    def test_synthesized_prompt(self, duplicate_check_log):
        result = parse_log(duplicate_check_log, "check_duplication_1<>2.json", "case-004")
        assert result.prompt == "[duplicate check — comparing two inputs]"

    def test_input_is_json_string_with_both(self, duplicate_check_log):
        result = parse_log(duplicate_check_log, "check_duplication_1<>2.json", "case-004")
        parsed_input = json.loads(result.input)
        assert "input1" in parsed_input
        assert "input2" in parsed_input
        assert parsed_input["input1"] == {"text": "doc A"}
        assert parsed_input["input2"] == {"text": "doc B"}

    def test_output_preserved(self, duplicate_check_log):
        result = parse_log(duplicate_check_log, "check_duplication_1<>2.json", "case-004")
        assert result.output == "not duplicate"

    def test_priority_over_standard(self):
        """input1/input2 keys take priority over prompt key detection."""
        raw = {
            "prompt": "Are these the same?",
            "input1": {"text": "A"},
            "input2": {"text": "B"},
            "output": "not duplicate",
        }
        result = parse_log(raw, "check_duplication_0<>1.json", "case-005")
        assert result.schema_variant == "duplicate_check"
