"""Local filesystem implementation of StorageProvider.

Useful for development and integration tests without cloud credentials.
The *base_dir* acts as the storage root; paths passed to the interface
methods are resolved relative to it.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from llm_judge.storage.base import StorageProvider

logger = logging.getLogger(__name__)


class LocalStorageProvider(StorageProvider):
    """StorageProvider backed by a local directory tree."""

    def __init__(self, base_dir: str) -> None:
        self._root = Path(base_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # StorageProvider interface
    # ------------------------------------------------------------------

    def list_files(
        self,
        prefix: str = "",
        modified_since: Optional[datetime] = None,
    ) -> Iterator[tuple[str, Optional[datetime]]]:
        search_root = self._root / prefix if prefix else self._root
        if not search_root.exists():
            return
        for dirpath, _dirs, filenames in os.walk(search_root):
            for name in filenames:
                full = Path(dirpath) / name
                rel = full.relative_to(self._root)
                rel_str = str(rel)
                mtime_ts = full.stat().st_mtime
                mtime = datetime.fromtimestamp(mtime_ts, tz=timezone.utc)
                if modified_since is not None and mtime < modified_since:
                    continue
                yield rel_str, mtime

    def read_file(self, path: str) -> str:
        return (self._root / path).read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        target = self._root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.debug("Wrote local file %s", target)

    def file_exists(self, path: str) -> bool:
        return (self._root / path).exists()
