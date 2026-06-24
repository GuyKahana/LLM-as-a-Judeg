"""Tests for golden_examples.load_golden_examples."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_judge import golden_examples
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
        mock_gcs_client.read_golden_examples.assert_called_once_with("extraction_list", 2)

    def test_bundled_fallback_used_when_bucket_empty(
        self, mock_gcs_client, config, tmp_path, monkeypatch
    ):
        """When the bucket has nothing, fall back to bundled examples in the repo."""
        rubric_dir = tmp_path / "full_summary"
        rubric_dir.mkdir()
        bundled = {"prompt": "p", "output": "o", "expected_verdict": "pass"}
        (rubric_dir / "example1.json").write_text(json.dumps(bundled), encoding="utf-8")

        monkeypatch.setattr(golden_examples, "_BUNDLED_GOLDEN_DIR", tmp_path)
        mock_gcs_client.read_golden_examples.return_value = []

        result = load_golden_examples(mock_gcs_client, "full_summary")
        assert result == [bundled]

    def test_bundled_fallback_skipped_when_bucket_has_examples(
        self, mock_gcs_client, config, tmp_path, monkeypatch
    ):
        """If the bucket has any examples, bundled goldens are ignored."""
        rubric_dir = tmp_path / "full_summary"
        rubric_dir.mkdir()
        (rubric_dir / "example1.json").write_text(
            json.dumps({"source": "bundled", "expected_verdict": "pass"}), encoding="utf-8"
        )
        monkeypatch.setattr(golden_examples, "_BUNDLED_GOLDEN_DIR", tmp_path)

        bucket_example = {"source": "bucket", "expected_verdict": "pass"}
        mock_gcs_client.read_golden_examples.return_value = [bucket_example]

        result = load_golden_examples(mock_gcs_client, "full_summary")
        assert result == [bucket_example]

    def test_bundled_fallback_caps_at_two(
        self, mock_gcs_client, config, tmp_path, monkeypatch
    ):
        rubric_dir = tmp_path / "full_summary"
        rubric_dir.mkdir()
        for i in range(5):
            (rubric_dir / f"example{i}.json").write_text(
                json.dumps({"i": i, "expected_verdict": "pass"}), encoding="utf-8"
            )
        monkeypatch.setattr(golden_examples, "_BUNDLED_GOLDEN_DIR", tmp_path)
        mock_gcs_client.read_golden_examples.return_value = []

        result = load_golden_examples(mock_gcs_client, "full_summary")
        assert len(result) == 2

    def test_warns_when_actual_below_configured_limit(
        self, mock_gcs_client, config, tmp_path, monkeypatch, caplog
    ):
        """Warn when the configured limit exceeds the number of available examples."""
        monkeypatch.setattr(golden_examples, "_BUNDLED_GOLDEN_DIR", tmp_path)
        mock_gcs_client.read_golden_examples.return_value = [
            {"prompt": "p", "expected_verdict": "pass"}
        ]
        with caplog.at_level("WARNING", logger="llm_judge.golden_examples"):
            result = load_golden_examples(mock_gcs_client, "full_summary", limit=5)
        assert len(result) == 1
        assert any(
            "Only 1 golden example" in rec.message and "requested up to 5" in rec.message
            for rec in caplog.records
        )

    def test_warns_when_zero_examples_available(
        self, mock_gcs_client, config, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.setattr(golden_examples, "_BUNDLED_GOLDEN_DIR", tmp_path)
        mock_gcs_client.read_golden_examples.return_value = []
        with caplog.at_level("WARNING", logger="llm_judge.golden_examples"):
            result = load_golden_examples(mock_gcs_client, "full_summary", limit=2)
        assert result == []
        assert any("Only 0 golden example" in rec.message for rec in caplog.records)

    def test_no_warning_when_actual_meets_limit(
        self, mock_gcs_client, config, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.setattr(golden_examples, "_BUNDLED_GOLDEN_DIR", tmp_path)
        mock_gcs_client.read_golden_examples.return_value = [
            {"i": 0, "expected_verdict": "pass"},
            {"i": 1, "expected_verdict": "pass"},
        ]
        with caplog.at_level("WARNING", logger="llm_judge.golden_examples"):
            load_golden_examples(mock_gcs_client, "full_summary", limit=2)
        assert not any(rec.levelname == "WARNING" for rec in caplog.records)

    def test_returns_empty_when_both_sources_empty(
        self, mock_gcs_client, config, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(golden_examples, "_BUNDLED_GOLDEN_DIR", tmp_path)
        mock_gcs_client.read_golden_examples.return_value = []
        result = load_golden_examples(mock_gcs_client, "full_summary")
        assert result == []

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
