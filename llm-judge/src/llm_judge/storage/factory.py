"""Factory that creates a StorageProvider for a given root/bucket.

Reads ``STORAGE_PROVIDER`` from config (default ``"gcs"``).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from llm_judge.storage.base import StorageProvider

if TYPE_CHECKING:
    from llm_judge.config import Settings


def create_provider(
    root: str,
    config: "Settings",
    provider: "str | None" = None,
) -> StorageProvider:
    """Return the appropriate :class:`StorageProvider` for *root*.

    *root* is the bucket name for cloud providers, or a base directory path
    for the local provider.

    Parameters
    ----------
    root:
        Bucket name (GCS/S3/Azure) or base directory path (local).
    config:
        Fully-populated Settings instance.
    provider:
        Backend to use for this root (``"gcs"``, ``"local"``, ``"s3"``,
        ``"azure"``).  When ``None``, falls back to ``config.storage_provider``.
        This is what lets different roots use different backends.
    """
    provider = (provider or config.storage_provider).lower()

    if provider == "gcs":
        from llm_judge.storage.gcs import GCSStorageProvider
        return GCSStorageProvider(bucket=root, config=config)

    if provider == "local":
        from llm_judge.storage.local import LocalStorageProvider
        base = config.local_storage_base_dir
        # For local, root is treated as a subdirectory under base_dir
        return LocalStorageProvider(base_dir=os.path.join(base, root))

    if provider == "s3":
        from llm_judge.storage.s3 import S3StorageProvider
        return S3StorageProvider(bucket=root, config=config)

    if provider == "azure":
        from llm_judge.storage.azure import AzureStorageProvider
        return AzureStorageProvider(container=root, config=config)

    raise ValueError(
        f"Unknown storage provider {provider!r} for root {root!r}. "
        "Check STORAGE_PROVIDER or the relevant per-root override "
        "(PRODUCTION_/VERDICT_/GOLDEN_STORAGE_PROVIDER). "
        "Supported values: gcs, local, s3, azure."
    )
