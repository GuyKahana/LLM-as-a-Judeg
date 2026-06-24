"""Tests for runner.run_batch."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from llm_judge.models import BlobMeta, Verdict
from llm_judge.runner import run_batch


def _make_blob(case_id: str = "case-001", filename: str = "full_summary.json") -> BlobMeta:
    return BlobMeta(case_id=case_id, filename=filename, modified_time=datetime.now(tz=timezone.utc))


def _make_verdict(case_id: str = "case-001", filename: str = "full_summary.json", flagged: bool = False) -> Verdict:
    return Verdict(
        case_id=case_id,
        filename=filename,
        prompt_type="full_summary",
        schema_variant="standard",
        score=4,
        per_criterion={},
        flagged=flagged,
        reasoning="Good.",
        parse_error=False,
    )


@pytest.fixture()
def mock_gcs(mock_gcs_client):
    """GCS client with one discoverable blob."""
    mock_gcs_client.list_logs_modified_since.return_value = iter([
        _make_blob("case-001", "full_summary.json"),
    ])
    mock_gcs_client.list_all_logs_for_case.return_value = iter([
        _make_blob("case-001", "full_summary.json"),
    ])
    mock_gcs_client.read_log.return_value = {
        "prompt": "Summarize.",
        "input": "Patient info.",
        "output": "Summary.",
    }
    mock_gcs_client.verdict_exists.return_value = False
    return mock_gcs_client


def _patch_run(mock_gcs, mock_llm_client, config, verdict=None):
    """Helper: patch StorageClient, LLMClient, evaluate_turn and call run_batch."""
    if verdict is None:
        verdict = _make_verdict()
    with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
         patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
         patch("llm_judge.runner.evaluate_turn", return_value=verdict) as mock_eval:
        summary = run_batch(config, dry_run_override=True)
    return summary, mock_eval


class TestSkipExisting:
    def test_skipped_existing_incremented(self, mock_gcs, mock_llm_client, config):
        mock_gcs.verdict_exists.return_value = True
        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client):
            summary = run_batch(config, dry_run_override=True)
        assert summary.skipped_existing == 1
        assert summary.evaluated == 0


class TestUnmapped:
    def test_unmapped_incremented(self, mock_gcs, mock_llm_client, config):
        mock_gcs.list_logs_modified_since.return_value = iter([
            _make_blob("case-001", "completely_unknown_file.json"),
        ])
        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client):
            summary = run_batch(config, dry_run_override=True)
        assert summary.unmapped == 1
        assert summary.evaluated == 0


class TestErrorHandling:
    def test_exception_in_evaluation_increments_errors_and_continues(self, mock_gcs, mock_llm_client, config):
        """One blob raises, run still completes with errors=1."""
        mock_gcs.list_logs_modified_since.return_value = iter([
            _make_blob("case-001", "full_summary.json"),
            _make_blob("case-002", "full_summary.json"),
        ])
        mock_gcs.read_log.return_value = {"prompt": "x", "input": "y", "output": "z"}

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Simulated evaluation failure")
            return _make_verdict("case-002")

        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
             patch("llm_judge.runner.evaluate_turn", side_effect=side_effect):
            summary = run_batch(config, dry_run_override=True)

        assert summary.errors == 1
        assert summary.evaluated == 1


class TestCaseIdIgnoresLookback:
    def test_case_id_calls_list_all(self, mock_gcs, mock_llm_client, config):
        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
             patch("llm_judge.runner.evaluate_turn", return_value=_make_verdict()):
            run_batch(config, case_id="case-001", dry_run_override=True)
        mock_gcs.list_all_logs_for_case.assert_called_once_with("case-001")
        mock_gcs.list_logs_modified_since.assert_not_called()

    def test_no_case_id_calls_modified_since(self, mock_gcs, mock_llm_client, config):
        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
             patch("llm_judge.runner.evaluate_turn", return_value=_make_verdict()):
            run_batch(config, dry_run_override=True)
        mock_gcs.list_logs_modified_since.assert_called_once()
        mock_gcs.list_all_logs_for_case.assert_not_called()


class TestMaxTurnsCap:
    def test_capped_at_max_turns(self, mock_gcs, mock_llm_client, config):
        config.judge_max_turns_per_run = 2
        blobs = [_make_blob(f"case-{i:03d}", "full_summary.json") for i in range(10)]
        mock_gcs.list_logs_modified_since.return_value = iter(blobs)
        mock_gcs.read_log.return_value = {"prompt": "x", "input": "y", "output": "z"}

        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
             patch("llm_judge.runner.evaluate_turn", return_value=_make_verdict()) as mock_eval:
            summary = run_batch(config, dry_run_override=True)

        # Only 2 evaluations should happen
        assert mock_eval.call_count <= 2
        assert summary.evaluated <= 2


class TestFlaggedItems:
    def test_flagged_verdict_appears_in_summary(self, mock_gcs, mock_llm_client, config):
        flagged_verdict = _make_verdict(flagged=True)
        flagged_verdict.reasoning = "This output is very bad indeed."
        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
             patch("llm_judge.runner.evaluate_turn", return_value=flagged_verdict):
            summary = run_batch(config, dry_run_override=True)
        assert summary.flagged == 1
        assert len(summary.flagged_items) == 1
        assert summary.flagged_items[0].case_id == "case-001"


class TestDryRun:
    def test_dry_run_skips_write_verdict(self, mock_gcs, mock_llm_client, config):
        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
             patch("llm_judge.runner.evaluate_turn", return_value=_make_verdict()):
            run_batch(config, dry_run_override=True)
        mock_gcs.write_verdict.assert_not_called()

    def test_dry_run_skips_run_summary_write(self, mock_gcs, mock_llm_client, config):
        """RunSummary must NOT be written when dry_run is True."""
        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
             patch("llm_judge.runner.evaluate_turn", return_value=_make_verdict()):
            run_batch(config, dry_run_override=True)
        mock_gcs._verdict.write_file.assert_not_called()


class TestRunId:
    def test_run_id_stamped_on_verdicts(self, mock_gcs, mock_llm_client, config):
        """run_id must be set on each verdict returned from _evaluate_one."""
        captured_verdicts: list[Verdict] = []

        original_evaluate = __import__("llm_judge.runner", fromlist=["_evaluate_one"])._evaluate_one

        def capturing_evaluate_one(blob, storage_client, llm_client, cfg, rubric_name, run_id=""):
            v = _make_verdict(blob.case_id, blob.filename)
            v.run_id = run_id
            captured_verdicts.append(v)
            return v

        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
             patch("llm_judge.runner._evaluate_one", side_effect=capturing_evaluate_one):
            summary = run_batch(config, dry_run_override=True)

        assert len(captured_verdicts) == 1
        assert captured_verdicts[0].run_id != ""
        assert captured_verdicts[0].run_id == summary.run_id

    def test_run_summary_written_when_not_dry_run(self, mock_gcs, mock_llm_client, config):
        """RunSummary is written to {runs_prefix}{run_id}.json when not dry_run."""
        config.runs_prefix = "runs/"
        with patch("llm_judge.runner.StorageClient", return_value=mock_gcs), \
             patch("llm_judge.runner.LLMClient", return_value=mock_llm_client), \
             patch("llm_judge.runner.evaluate_turn", return_value=_make_verdict()):
            summary = run_batch(config, dry_run_override=False)

        mock_gcs._verdict.write_file.assert_called_once()
        call_args = mock_gcs._verdict.write_file.call_args
        path_arg = call_args[0][0]
        assert path_arg == f"runs/{summary.run_id}.json"
        # Verify the written content is valid JSON containing the run_id
        content_arg = call_args[0][1]
        parsed = json.loads(content_arg)
        assert parsed["run_id"] == summary.run_id
