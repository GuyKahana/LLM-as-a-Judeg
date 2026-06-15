"""Azure Blob Storage provider stub.

Not implemented in v1.  Set ``STORAGE_PROVIDER=azure`` to surface this error
at startup rather than silently falling back to another provider.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterator, Optional

from llm_judge.storage.base import StorageProvider

_MSG = (
    "AzureStorageProvider is not implemented. "
    "Use STORAGE_PROVIDER=gcs or STORAGE_PROVIDER=local."
)


class AzureStorageProvider(StorageProvider):
    def __init__(self, container: str, config: object) -> None:  # noqa: ARG002
        raise NotImplementedError(_MSG)

    def list_files(
        self, prefix: str = "", modified_since: Optional[datetime] = None
    ) -> Iterator[tuple[str, Optional[datetime]]]:
        raise NotImplementedError(_MSG)

    def read_file(self, path: str) -> str:
        raise NotImplementedError(_MSG)

    def write_file(self, path: str, content: str) -> None:
        raise NotImplementedError(_MSG)

    def file_exists(self, path: str) -> bool:
        raise NotImplementedError(_MSG)
