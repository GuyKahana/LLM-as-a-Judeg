"""Shared pytest fixtures for LLM Judge tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_judge.config import Settings
from llm_judge.models import BlobMeta

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def config() -> Settings:
    """A minimal Settings instance suitable for unit tests."""
    return Settings(
        production_bucket="test-production-bucket",
        verdict_bucket="test-verdict-bucket",
        judge_llm_api_key="sk-ant-test-key-1234",
        judge_llm_provider="anthropic",
        judge_model="claude-sonnet-4-6",
        judge_score_threshold=3,
        judge_lookback_hours=24,
        judge_max_turns_per_run=500,
        judge_max_workers=2,
        judge_input_truncate_chars=150_000,
        judge_parse_error_threshold=10,
        alert_on_success=True,
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# GCS client mock
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_gcs_client() -> MagicMock:
    """A MagicMock that mimics StorageClient."""
    client = MagicMock()
    client.verdict_exists.return_value = False
    client.write_verdict.return_value = None
    client.read_golden_examples.return_value = []
    return client


# ---------------------------------------------------------------------------
# LLM client mock
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_llm_client() -> MagicMock:
    """A MagicMock that mimics LLMClient returning a clean verdict JSON."""
    client = MagicMock()
    client.judge.return_value = json.dumps({
        "score": 4,
        "per_criterion": {"completeness": 4, "accuracy": 4},
        "flagged": False,
        "reasoning": "The output is good.",
    })
    return client


# ---------------------------------------------------------------------------
# Fixture loaders
# ---------------------------------------------------------------------------

def load_fixture(name: str) -> dict:
    """Load a JSON fixture file by name."""
    path = FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def standard_log() -> dict:
    return load_fixture("standard_log.json")


@pytest.fixture()
def tool_use_log() -> dict:
    return load_fixture("tool_use_log.json")


@pytest.fixture()
def boundary_check_log() -> dict:
    return load_fixture("boundary_check_log.json")


@pytest.fixture()
def duplicate_check_log() -> dict:
    return load_fixture("duplicate_check_log.json")


@pytest.fixture()
def golden_example() -> dict:
    return load_fixture("golden_example.json")
