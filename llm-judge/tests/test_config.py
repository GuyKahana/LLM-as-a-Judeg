"""Tests for config.Settings."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from llm_judge.config import Settings


class TestGoldenBucketDefault:
    def test_golden_bucket_defaults_to_verdict_bucket(self):
        settings = Settings(
            production_bucket="prod-bucket",
            verdict_bucket="verdict-bucket",
            judge_llm_api_key="sk-ant-test-1234",
            # golden_bucket NOT set
        )
        assert settings.golden_bucket == "verdict-bucket"

    def test_golden_bucket_explicit_overrides(self):
        settings = Settings(
            production_bucket="prod-bucket",
            verdict_bucket="verdict-bucket",
            golden_bucket="separate-golden-bucket",
            judge_llm_api_key="sk-ant-test-1234",
        )
        assert settings.golden_bucket == "separate-golden-bucket"

    def test_golden_bucket_not_changed_when_both_same(self):
        settings = Settings(
            production_bucket="prod-bucket",
            verdict_bucket="my-bucket",
            golden_bucket="my-bucket",
            judge_llm_api_key="sk-ant-test-1234",
        )
        assert settings.golden_bucket == "my-bucket"


class TestLocalStorageBaseDir:
    def test_relative_base_dir_anchored_to_project_root(self):
        """A relative LOCAL_STORAGE_BASE_DIR becomes absolute under llm-judge/."""
        import os

        settings = Settings(
            production_bucket="prod",
            verdict_bucket="verdict",
            judge_llm_api_key="sk-ant-test-1234",
            local_storage_base_dir="./local-data",
        )
        assert os.path.isabs(settings.local_storage_base_dir)
        assert settings.local_storage_base_dir.endswith("/llm-judge/local-data")

    def test_absolute_base_dir_left_untouched(self):
        settings = Settings(
            production_bucket="prod",
            verdict_bucket="verdict",
            judge_llm_api_key="sk-ant-test-1234",
            local_storage_base_dir="/tmp/judge-data",
        )
        assert settings.local_storage_base_dir == "/tmp/judge-data"


class TestLLMBaseUrl:
    def test_base_url_passed_to_anthropic_constructor(self):
        """When JUDGE_LLM_BASE_URL is set, it should reach the Anthropic constructor."""
        from llm_judge.llm_client import LLMClient

        settings = Settings(
            production_bucket="prod",
            verdict_bucket="verdict",
            judge_llm_api_key="sk-ant-test-1234",
            judge_llm_base_url="https://my-proxy.internal/v1",
        )
        with patch("llm_judge.llm_client.anthropic.Anthropic") as mock_anthropic:
            LLMClient(settings)
        mock_anthropic.assert_called_once()
        _, kwargs = mock_anthropic.call_args
        assert kwargs.get("base_url") == "https://my-proxy.internal/v1"

    def test_no_base_url_not_passed_to_anthropic(self):
        from llm_judge.llm_client import LLMClient

        settings = Settings(
            production_bucket="prod",
            verdict_bucket="verdict",
            judge_llm_api_key="sk-ant-test-1234",
            judge_llm_base_url=None,
        )
        with patch("llm_judge.llm_client.anthropic.Anthropic") as mock_anthropic:
            LLMClient(settings)
        _, kwargs = mock_anthropic.call_args
        assert "base_url" not in kwargs


class TestApiKeyMasking:
    def test_masked_key_shows_only_last_four(self):
        settings = Settings(
            production_bucket="prod",
            verdict_bucket="verdict",
            judge_llm_api_key="sk-ant-abcdefgh",
        )
        masked = settings.masked_api_key()
        # Last 4 chars of "sk-ant-abcdefgh" are "efgh"
        assert masked.endswith("efgh")
        # The plain-text prefix must not appear
        assert "sk-ant-abcd" not in masked
        # Should be mostly asterisks
        assert masked.startswith("*")

    def test_short_key_fully_masked(self):
        settings = Settings(
            production_bucket="prod",
            verdict_bucket="verdict",
            judge_llm_api_key="abc",
        )
        assert settings.masked_api_key() == "****"


class TestProviderNotImplemented:
    def test_non_anthropic_provider_raises(self):
        from llm_judge.llm_client import LLMClient

        settings = Settings(
            production_bucket="prod",
            verdict_bucket="verdict",
            judge_llm_api_key="sk-ant-test-1234",
            judge_llm_provider="openai",
        )
        with pytest.raises(NotImplementedError, match="openai"):
            LLMClient(settings)
