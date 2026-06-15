"""Google Cloud Storage implementation of StorageProvider."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterator, Optional

from google.cloud import storage  # type: ignore[import-untyped]

from llm_judge.storage.base import StorageProvider

if TYPE_CHECKING:
    from llm_judge.config import Settings

logger = logging.getLogger(__name__)


class GCSStorageProvider(StorageProvider):
    """StorageProvider backed by a single GCS bucket."""

    def __init__(self, bucket: str, config: "Settings") -> None:
        self._bucket_name = bucket
        kwargs: dict = {}
        if config.gcp_project_id:
            kwargs["project"] = config.gcp_project_id
        self._client = storage.Client(**kwargs)
        self._bucket = self._client.bucket(bucket)

    # ------------------------------------------------------------------
    # StorageProvider interface
    # ------------------------------------------------------------------

    def list_files(
        self,
        prefix: str = "",
        modified_since: Optional[datetime] = None,
    ) -> Iterator[tuple[str, Optional[datetime]]]:
        blobs = self._client.list_blobs(self._bucket, prefix=prefix)
        for blob in blobs:
            updated: Optional[datetime] = blob.updated
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if modified_since is not None and (updated is None or updated < modified_since):
                continue
            yield blob.name, updated

    def read_file(self, path: str) -> str:
        blob = self._bucket.blob(path)
        return blob.download_as_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        blob = self._bucket.blob(path)
        blob.upload_from_string(content, content_type="application/json")
        logger.debug("Wrote gs://%s/%s", self._bucket_name, path)

    def file_exists(self, path: str) -> bool:
        return self._bucket.blob(path).exists()
