"""Tests for golden_examples.load_golden_examples."""

from __future__ import annotations

import pytest

from llm_judge.golden_examples import load_golden_examples


class TestLoadGoldenExamples:
    def test_empty_list_when_gcs_returns_none(self, mock_gcs_client, config):
        mock_gcs_client.read_golden_examples.return_value = []
        result = load_golden_examples(mock_gcs_client, "final_summary")
        assert result == []

    def test_max_two_returned_when_five_present(self, mock_gcs_client, config):
        five_examples = [
            {"prompt": f"Example {i}", "output": f"Output {i}", "expected_verdict": "pass"}
            for i in range(5)
        ]
        # StorageClient already caps at 2, but load_golden_examples adds a defensive cap too
        # Simulate StorageClient returning 5 (in case the client-level cap is bypassed)
        mock_gcs_client.read_golden_examples.return_value = five_examples
        result = load_golden_examples(mock_gcs_client, "final_summary")
        assert len(result) == 2

    def test_returns_all_when_fewer_than_two(self, mock_gcs_client, config):
        one_example = [{"prompt": "Test", "output": "Good", "expected_verdict": "pass"}]
        mock_gcs_client.read_golden_examples.return_value = one_example
        result = load_golden_examples(mock_gcs_client, "final_summary")
        assert len(result) == 1

    def test_prompt_type_forwarded_to_gcs(self, mock_gcs_client, config):
        mock_gcs_client.read_golden_examples.return_value = []
        load_golden_examples(mock_gcs_client, "extraction_list")
        mock_gcs_client.read_golden_examples.assert_called_once_with("extraction_list")

    def test_returned_dicts_intact(self, mock_gcs_client, config):
        example = {
            "prompt": "Summarize.",
            "input": "Patient info.",
            "output": "Summary.",
            "expected_verdict": "pass",
        }
        mock_gcs_client.read_golden_examples.return_value = [example]
        result = load_golden_examples(mock_gcs_client, "final_summary")
        assert result[0] == example
