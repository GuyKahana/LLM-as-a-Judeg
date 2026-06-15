"""Abstract storage provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterator, Optional


class StorageProvider(ABC):
    """File-storage abstraction over a single root (bucket / directory).

    All paths passed to and returned from these methods are relative to the
    root that was supplied at construction time.
    """

    @abstractmethod
    def list_files(
        self,
        prefix: str = "",
        modified_since: Optional[datetime] = None,
    ) -> Iterator[tuple[str, Optional[datetime]]]:
        """Yield ``(relative_path, modified_time)`` for every file under *prefix*.

        *modified_since* is an optional UTC datetime; when given, only files
        with a modification time >= the cutoff should be yielded.  Providers
        that cannot determine modification time must yield the file with
        ``modified_time=None`` and let the caller decide.
        """

    @abstractmethod
    def read_file(self, path: str) -> str:
        """Return the UTF-8 text content of *path*."""

    @abstractmethod
    def write_file(self, path: str, content: str) -> None:
        """Write *content* (UTF-8 text) to *path*, creating it if necessary."""

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """Return ``True`` if *path* exists in this root."""
