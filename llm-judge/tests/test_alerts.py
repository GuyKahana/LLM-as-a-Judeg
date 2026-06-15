"""Tests for alerts.send_digest."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from llm_judge.alerts import send_digest
from llm_judge.models import RunSummary


def _make_summary(flagged: int = 0, parse_errors: int = 0, errors: int = 0) -> RunSummary:
    now = datetime.now(tz=timezone.utc)
    return RunSummary(
        run_id="test-run-001",
        started_at=now,
        finished_at=now,
        total_logs=10,
        evaluated=8,
        skipped_existing=1,
        unmapped=1,
        flagged=flagged,
        errors=errors,
        parse_errors=parse_errors,
        by_prompt_type={"final_summary": 8},
        flagged_items=[],
    )


class TestAlertOnSuccess:
    def test_always_sends_when_alert_on_success_true(self, config):
        """ALERT_ON_SUCCESS=true: sends even with 0 flags, 0 errors."""
        config.alert_on_success = True
        config.alert_webhook_url = "https://hooks.example.com/webhook"
        summary = _make_summary(flagged=0, parse_errors=0)

        with patch("llm_judge.alerts._send_webhook") as mock_webhook:
            send_digest(summary, config, dry_run=False)
        mock_webhook.assert_called_once()

    def test_skips_when_alert_on_success_false_no_flags(self, config):
        """ALERT_ON_SUCCESS=false, 0 flags, 0 parse_errors: no send."""
        config.alert_on_success = False
        config.alert_webhook_url = "https://hooks.example.com/webhook"
        config.judge_parse_error_threshold = 10
        summary = _make_summary(flagged=0, parse_errors=0)

        with patch("llm_judge.alerts._send_webhook") as mock_webhook:
            send_digest(summary, config, dry_run=False)
        mock_webhook.assert_not_called()

    def test_sends_when_alert_on_success_false_but_flagged(self, config):
        """ALERT_ON_SUCCESS=false but flagged > 0: should still send."""
        config.alert_on_success = False
        config.alert_webhook_url = "https://hooks.example.com/webhook"
        summary = _make_summary(flagged=1, parse_errors=0)

        with patch("llm_judge.alerts._send_webhook") as mock_webhook:
            send_digest(summary, config, dry_run=False)
        mock_webhook.assert_called_once()

    def test_sends_when_parse_errors_exceed_threshold(self, config):
        """ALERT_ON_SUCCESS=false, parse_errors > threshold → force send."""
        config.alert_on_success = False
        config.judge_parse_error_threshold = 5
        config.alert_webhook_url = "https://hooks.example.com/webhook"
        summary = _make_summary(flagged=0, parse_errors=11)

        with patch("llm_judge.alerts._send_webhook") as mock_webhook:
            send_digest(summary, config, dry_run=False)
        mock_webhook.assert_called_once()

    def test_no_send_when_parse_errors_at_threshold(self, config):
        """parse_errors == threshold (not exceeding): no force send."""
        config.alert_on_success = False
        config.judge_parse_error_threshold = 10
        config.alert_webhook_url = "https://hooks.example.com/webhook"
        summary = _make_summary(flagged=0, parse_errors=10)  # exactly at threshold, not exceeding

        with patch("llm_judge.alerts._send_webhook") as mock_webhook:
            send_digest(summary, config, dry_run=False)
        mock_webhook.assert_not_called()


class TestWebhookPayload:
    def test_webhook_called_with_correct_shape(self, config):
        config.alert_webhook_url = "https://hooks.example.com/webhook"
        config.alert_on_success = True
        summary = _make_summary(flagged=2, parse_errors=1)

        captured: list[dict] = []

        def fake_send_webhook(payload, url):
            captured.append(payload)

        with patch("llm_judge.alerts._send_webhook", side_effect=fake_send_webhook):
            send_digest(summary, config, dry_run=False)

        assert len(captured) == 1
        p = captured[0]
        assert p["run_id"] == "test-run-001"
        assert p["total_logs"] == 10
        assert p["evaluated"] == 8
        assert p["flagged"] == 2
        assert p["parse_errors"] == 1
        assert "flagged_items" in p
        assert "by_prompt_type" in p
        assert "started_at" in p
        assert "finished_at" in p


class TestEmailNotSentWithoutSmtp:
    def test_no_email_when_smtp_host_not_set(self, config):
        config.smtp_host = None
        config.alert_emails = "test@example.com"
        config.alert_on_success = True
        summary = _make_summary()

        with patch("llm_judge.alerts._send_email") as mock_email:
            send_digest(summary, config, dry_run=False)
        mock_email.assert_not_called()


class TestDryRun:
    def test_dry_run_skips_webhook(self, config):
        config.alert_webhook_url = "https://hooks.example.com/webhook"
        config.alert_on_success = True
        summary = _make_summary()

        with patch("llm_judge.alerts._send_webhook") as mock_webhook:
            send_digest(summary, config, dry_run=True)
        mock_webhook.assert_not_called()

    def test_dry_run_skips_email(self, config):
        config.smtp_host = "smtp.example.com"
        config.alert_emails = "test@example.com"
        config.alert_on_success = True
        summary = _make_summary()

        with patch("llm_judge.alerts._send_email") as mock_email:
            send_digest(summary, config, dry_run=True)
        mock_email.assert_not_called()
