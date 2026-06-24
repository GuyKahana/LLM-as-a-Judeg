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

    # Per-root provider overrides.  Each is optional; when unset it falls back
    # to ``storage_provider`` (golden falls back to the *verdict* provider,
    # mirroring how ``golden_bucket`` defaults to ``verdict_bucket``).  This lets
    # a single root use a different backend than the rest — e.g. read production
    # logs from GCS while writing verdicts to the local filesystem.
    production_storage_provider: Optional[str] = None
    verdict_storage_provider: Optional[str] = None
    golden_storage_provider: Optional[str] = None

    # -------------------------------------------------------------------------
    # Buckets / roots (bucket names for GCS; subdirectory names for local)
    # -------------------------------------------------------------------------
    production_bucket: str
    verdict_bucket: str
    golden_bucket: Optional[str] = None
    verdict_prefix: str = "judge/"
    golden_prefix: str = "golden/"
    runs_prefix: str = "runs/"

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
    # Judge model sampling parameters
    # Set only the params supported by your model:
    #   - Opus 4.7+, Fable 5: use judge_effort; temperature/top_p/top_k will 400
    #   - Sonnet 4.6, Opus 4.6 and older: use temperature OR top_p (not both)
    # -------------------------------------------------------------------------
    judge_max_tokens: int = 4096
    judge_temperature: Optional[float] = None       # 0.0–1.0; not for Opus 4.7+
    judge_top_p: Optional[float] = None             # 0.0–1.0; not for Opus 4.7+; mutually exclusive with temperature
    judge_top_k: Optional[int] = None               # not for Opus 4.7+
    judge_effort: Optional[str] = None              # "low"|"medium"|"high"|"xhigh"|"max"; Opus 4.6+ and Sonnet 4.6+

    # -------------------------------------------------------------------------
    # Judging behaviour
    # -------------------------------------------------------------------------
    judge_score_threshold: int = 3
    judge_lookback_hours: int = 24
    judge_max_turns_per_run: int = 500
    judge_max_workers: int = 5
    judge_input_truncate_chars: int = 150_000
    judge_parse_error_threshold: int = 10
    judge_golden_examples_max: int = 2

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

    @model_validator(mode="after")
    def resolve_per_root_providers(self) -> "Settings":
        """Fill in each per-root provider from the appropriate fallback.

        production/verdict fall back to ``storage_provider``; golden falls back
        to the (already-resolved) verdict provider, mirroring how ``golden_bucket``
        defaults to ``verdict_bucket``.  After this runs, all three are concrete
        strings, so :class:`StorageClient` never has to know about the fallback.
        """
        if self.production_storage_provider is None:
            self.production_storage_provider = self.storage_provider
        if self.verdict_storage_provider is None:
            self.verdict_storage_provider = self.storage_provider
        if self.golden_storage_provider is None:
            self.golden_storage_provider = self.verdict_storage_provider
        return self

    @model_validator(mode="after")
    def validate_sampling_params(self) -> "Settings":
        if self.judge_temperature is not None and self.judge_top_p is not None:
            raise ValueError(
                "JUDGE_TEMPERATURE and JUDGE_TOP_P are mutually exclusive — set only one."
            )
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
