"""Application boundary for AQR-014 recovery and portability.

The application layer only orchestrates a recovery gateway. SQLite, filesystem and
archive mechanics remain behind the gateway implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RecoveryArtifact:
    """One product artifact ready for download by the presentation layer."""

    filename: str
    media_type: str
    content: bytes
    summary: dict


class RecoveryGateway(Protocol):
    """Infrastructure port used by the recovery application use cases."""

    def inspect_installation(self, db_path: Path) -> dict: ...

    def create_backup(self, db_path: Path, output_path: Path) -> dict: ...

    def restore_backup(self, package_path: Path, target_db_path: Path) -> dict: ...

    def create_portable_export(self, db_path: Path, output_path: Path) -> dict: ...


class RecoveryApplication:
    """Framework-neutral AQR-014 use cases."""

    def __init__(self, gateway: RecoveryGateway):
        self._gateway = gateway

    def inspect_installation(self, db_path: Path) -> dict:
        return self._gateway.inspect_installation(Path(db_path))

    def create_backup(self, db_path: Path, output_path: Path) -> dict:
        return self._gateway.create_backup(Path(db_path), Path(output_path))

    def restore_backup(self, package_path: Path, target_db_path: Path) -> dict:
        return self._gateway.restore_backup(Path(package_path), Path(target_db_path))

    def create_portable_export(self, db_path: Path, output_path: Path) -> dict:
        return self._gateway.create_portable_export(Path(db_path), Path(output_path))


__all__ = ["RecoveryApplication", "RecoveryArtifact", "RecoveryGateway"]
