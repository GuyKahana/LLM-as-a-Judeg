"""Alert / digest sending logic."""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from llm_judge.config import Settings
from llm_judge.models import RunSummary

logger = logging.getLogger(__name__)


def _build_payload(summary: RunSummary) -> dict:
    """Build the webhook payload dict from a RunSummary."""
    return {
        "run_id": summary.run_id,
        "started_at": summary.started_at.isoformat(),
        "finished_at": summary.finished_at.isoformat(),
        "total_logs": summary.total_logs,
        "evaluated": summary.evaluated,
        "flagged": summary.flagged,
        "errors": summary.errors,
        "parse_errors": summary.parse_errors,
        "flagged_items": [item.model_dump(mode="json") for item in summary.flagged_items],
        "by_prompt_type": summary.by_prompt_type,
    }


def _build_html_body(summary: RunSummary) -> str:
    """Build a simple HTML email body for the digest."""
    flagged_rows = "".join(
        f"<tr>"
        f"<td>{item.case_id}</td>"
        f"<td>{item.filename}</td>"
        f"<td>{item.prompt_type}</td>"
        f"<td>{item.score if item.score is not None else 'N/A'}</td>"
        f"<td>{item.reasoning_snippet}</td>"
        f"</tr>"
        for item in summary.flagged_items
    )
    flagged_section = (
        f"<h3>Flagged Items ({summary.flagged})</h3>"
        "<table border='1' cellpadding='4' cellspacing='0'>"
        "<tr><th>Case ID</th><th>Filename</th><th>Prompt Type</th>"
        "<th>Score</th><th>Reasoning (snippet)</th></tr>"
        f"{flagged_rows}"
        "</table>"
        if summary.flagged_items
        else "<p>No flagged items.</p>"
    )

    by_type_rows = "".join(
        f"<tr><td>{ptype}</td><td>{count}</td></tr>"
        for ptype, count in summary.by_prompt_type.items()
    )

    duration = (summary.finished_at - summary.started_at).total_seconds()

    return f"""
<html><body>
<h2>LLM Judge Daily Digest</h2>
<p><strong>Run ID:</strong> {summary.run_id}</p>
<p><strong>Started:</strong> {summary.started_at.isoformat()}</p>
<p><strong>Finished:</strong> {summary.finished_at.isoformat()} ({duration:.1f}s)</p>
<h3>Summary</h3>
<table border='1' cellpadding='4' cellspacing='0'>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Total logs scanned</td><td>{summary.total_logs}</td></tr>
  <tr><td>Evaluated</td><td>{summary.evaluated}</td></tr>
  <tr><td>Skipped (verdict exists)</td><td>{summary.skipped_existing}</td></tr>
  <tr><td>Unmapped (no rubric)</td><td>{summary.unmapped}</td></tr>
  <tr><td>Flagged</td><td>{summary.flagged}</td></tr>
  <tr><td>Errors</td><td>{summary.errors}</td></tr>
  <tr><td>Parse errors</td><td>{summary.parse_errors}</td></tr>
</table>
<h3>By Prompt Type</h3>
<table border='1' cellpadding='4' cellspacing='0'>
  <tr><th>Prompt Type</th><th>Count</th></tr>
  {by_type_rows}
</table>
{flagged_section}
</body></html>
"""


def _should_send(summary: RunSummary, config: Settings) -> bool:
    """Return True if the digest should be sent (considering ALERT_ON_SUCCESS)."""
    if config.alert_on_success:
        return True
    # Force-send if there are flags or parse errors above threshold
    if summary.flagged > 0:
        return True
    if summary.parse_errors > config.judge_parse_error_threshold:
        return True
    return False


def _send_webhook(payload: dict, webhook_url: str) -> None:
    """POST the payload as JSON to the webhook URL."""
    body = json.dumps(payload, default=str).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        status = resp.status
    logger.info("Webhook response status=%d", status)


def _send_email(html_body: str, config: Settings) -> None:
    """Send the digest email to all configured recipients via SMTP."""
    if not config.smtp_host:
        logger.debug("SMTP host not configured; skipping email.")
        return
    if not config.alert_emails:
        logger.debug("No alert_emails configured; skipping email.")
        return

    recipients = [addr.strip() for addr in config.alert_emails.split(",") if addr.strip()]
    if not recipients:
        return

    for recipient in recipients:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "LLM Judge Daily Digest"
        msg["From"] = config.smtp_from or config.smtp_user or "llm-judge@localhost"
        msg["To"] = recipient
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
                server.ehlo()
                server.starttls()
                if config.smtp_user and config.smtp_password:
                    server.login(config.smtp_user, config.smtp_password)
                server.sendmail(msg["From"], [recipient], msg.as_string())
            logger.info("Digest email sent to %s", recipient)
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", recipient, exc)


def send_digest(summary: RunSummary, config: Settings, dry_run: bool = False) -> None:
    """Log the run summary and optionally send webhook / email alerts.

    The digest is always logged as structured JSON to stdout.

    Sending behaviour:
    - Always send if ``config.alert_on_success`` is True.
    - Always send if ``summary.flagged > 0``.
    - Always send if ``summary.parse_errors > config.judge_parse_error_threshold``.
    - Otherwise (``ALERT_ON_SUCCESS=false``, no flags, errors within threshold): skip.

    When ``dry_run`` is True, only log and return without sending.
    """
    payload = _build_payload(summary)

    # Always log
    logger.info("Run digest", extra={"digest": payload})

    should_send = _should_send(summary, config)

    if not should_send:
        logger.info(
            "Skipping alert dispatch (ALERT_ON_SUCCESS=false, no flags, "
            "parse_errors=%d <= threshold=%d)",
            summary.parse_errors,
            config.judge_parse_error_threshold,
        )
        return

    if dry_run:
        logger.info(
            "DRY_RUN: would send digest",
            extra={"digest": payload},
        )
        return

    # Webhook
    if config.alert_webhook_url:
        try:
            _send_webhook(payload, config.alert_webhook_url)
        except Exception as exc:
            logger.error("Webhook send failed: %s", exc)

    # Email
    if config.smtp_host and config.alert_emails:
        html_body = _build_html_body(summary)
        _send_email(html_body, config)
