"""Configuration via pydantic-settings – all values sourced from environment variables."""

from __future__ import annotations

from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Storage backend
    # -------------------------------------------------------------------------
    storage_provider: str = "gcs"
    local_storage_base_dir: str = "local-data"

    # -------------------------------------------------------------------------
    # Buckets / roots (bucket names for GCS; subdirectory names for local)
    # -------------------------------------------------------------------------
    production_bucket: str
    verdict_bucket: str
    golden_bucket: Optional[str] = None
    verdict_prefix: str = "judge/"
    golden_prefix: str = "golden/"

    # -------------------------------------------------------------------------
    # GCP
    # -------------------------------------------------------------------------
    gcp_project_id: Optional[str] = None
    google_application_credentials: Optional[str] = None

    # -------------------------------------------------------------------------
    # LLM / Judge model
    # -------------------------------------------------------------------------
    judge_model: str = "claude-sonnet-4-6"
    judge_llm_base_url: Optional[str] = None
    judge_llm_api_key: str
    judge_llm_provider: str = "anthropic"

    # -------------------------------------------------------------------------
    # Judging behaviour
    # -------------------------------------------------------------------------
    judge_score_threshold: int = 3
    judge_lookback_hours: int = 24
    judge_max_turns_per_run: int = 500
    judge_max_workers: int = 5
    judge_input_truncate_chars: int = 150_000
    judge_parse_error_threshold: int = 10

    # -------------------------------------------------------------------------
    # Alerting
    # -------------------------------------------------------------------------
    alert_webhook_url: Optional[str] = None
    alert_emails: Optional[str] = None
    alert_on_success: bool = True

    # -------------------------------------------------------------------------
    # SMTP (required only when alert_emails is set)
    # -------------------------------------------------------------------------
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None

    # -------------------------------------------------------------------------
    # Dry-run flag
    # -------------------------------------------------------------------------
    dry_run: bool = False

    # -------------------------------------------------------------------------
    # Model validator
    # -------------------------------------------------------------------------
    @model_validator(mode="after")
    def set_golden_bucket_default(self) -> "Settings":
        """If GOLDEN_BUCKET is not supplied, default it to VERDICT_BUCKET."""
        if self.golden_bucket is None:
            self.golden_bucket = self.verdict_bucket
        return self

    # -------------------------------------------------------------------------
    # Convenience helpers
    # -------------------------------------------------------------------------
    def masked_api_key(self) -> str:
        """Return the API key with all but the last 4 chars masked."""
        key = self.judge_llm_api_key
        if len(key) <= 4:
            return "****"
        return f"{'*' * (len(key) - 4)}{key[-4:]}"
