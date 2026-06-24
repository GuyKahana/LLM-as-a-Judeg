"""Domain-level storage client for the LLM Judge service.

Wraps three :class:`StorageProvider` instances (one per logical bucket) and
exposes judge-specific operations in terms of the abstract provider interface.
No GCS, S3, or Azure SDK types appear here.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Iterator, Optional

from llm_judge.models import BlobMeta
from llm_judge.storage.base import StorageProvider
from llm_judge.storage.factory import create_provider

if TYPE_CHECKING:
    from llm_judge.config import Settings

logger = logging.getLogger(__name__)


class StorageClient:
    """High-level judge storage operations backed by a :class:`StorageProvider`.

    Three separate providers handle access to the three logical storage roots:

    - ``_prod``    — production logs (read-only)
    - ``_verdict`` — verdict output (read/write)
    - ``_golden``  — golden examples (read-only)
    """

    def __init__(self, config: "Settings") -> None:
        self._config = config
        # Each root may use a different backend.  The per-root providers are
        # resolved (with fallbacks) by the Settings model validator, so they are
        # concrete strings by the time we get here.
        self._prod: StorageProvider = create_provider(
            config.production_bucket, config, config.production_storage_provider
        )
        self._verdict: StorageProvider = create_provider(
            config.verdict_bucket, config, config.verdict_storage_provider
        )
        # golden_bucket defaults to verdict_bucket (set by model_validator in config)
        self._golden: StorageProvider = create_provider(
            config.golden_bucket, config, config.golden_storage_provider  # type: ignore[arg-type]
        )

    # ------------------------------------------------------------------
    # Production log reading (READ-ONLY on production root)
    # ------------------------------------------------------------------

    def list_logs_modified_since(self, hours: int) -> Iterator[BlobMeta]:
        """Yield :class:`BlobMeta` for every log modified within *hours*."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        for path, modified_time in self._prod.list_files("logs/", modified_since=cutoff):
            meta = self._path_to_blob_meta(path, modified_time)
            if meta is not None:
                yield meta

    def list_all_logs_for_case(self, case_id: str) -> Iterator[BlobMeta]:
        """Yield :class:`BlobMeta` for ALL logs belonging to *case_id* (no time filter)."""
        prefix = f"logs/{case_id}/"
        for path, modified_time in self._prod.list_files(prefix):
            meta = self._path_to_blob_meta(path, modified_time)
            if meta is not None:
                yield meta

    def read_log(self, case_id: str, filename: str) -> dict:
        """Download and parse a single log JSON from the production root."""
        path = f"logs/{case_id}/{filename}"
        raw = self._prod.read_file(path)
        return json.loads(raw)

    # ------------------------------------------------------------------
    # Verdict I/O (WRITE to verdict root only)
    # ------------------------------------------------------------------

    def verdict_exists(self, case_id: str, filename: str) -> bool:
        """Return ``True`` if a verdict already exists for this log entry."""
        path = f"{self._config.verdict_prefix}{case_id}/{filename}"
        return self._verdict.file_exists(path)

    def write_verdict(self, case_id: str, filename: str, verdict: dict) -> None:
        """Write *verdict* JSON to the verdict root.  Never touches the production root."""
        path = f"{self._config.verdict_prefix}{case_id}/{filename}"
        content = json.dumps(verdict, default=str, indent=2)
        self._verdict.write_file(path, content)
        logger.debug("Wrote verdict to %s/%s", self._config.verdict_bucket, path)

    # ------------------------------------------------------------------
    # Golden examples (read from golden root)
    # ------------------------------------------------------------------

    def read_golden_examples(self, prompt_type: str) -> list[dict]:
        """Return up to ``judge_golden_examples_max`` golden example dicts for *prompt_type*."""
        prefix = f"{self._config.golden_prefix}{prompt_type}/"
        paths_and_times = list(self._golden.list_files(prefix))
        limit = self._config.judge_golden_examples_max
        json_paths = [p for p, _ in paths_and_times if p.endswith(".json")][:limit]

        results: list[dict] = []
        for path in json_paths:
            try:
                raw = self._golden.read_file(path)
                results.append(json.loads(raw))
            except Exception as exc:
                logger.warning("Failed to read golden example %s: %s", path, exc)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _path_to_blob_meta(path: str, modified_time: Optional[datetime]) -> Optional[BlobMeta]:
        """Parse ``logs/{case_id}/{filename}`` into a :class:`BlobMeta`."""
        parts = path.split("/")
        if len(parts) < 3:
            logger.debug("Skipping blob with unexpected path structure: %s", path)
            return None
        case_id = parts[1]
        filename = parts[-1]
        if not filename:
            return None
        return BlobMeta(case_id=case_id, filename=filename, modified_time=modified_time)
