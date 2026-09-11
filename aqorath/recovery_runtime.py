"""AQR-014 composition root for the local product surface."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .recovery_application import RecoveryApplication, RecoveryArtifact
from .recovery_infrastructure import SqliteRecoveryGateway
from .storage import get_db_path


_APPLICATION = RecoveryApplication(SqliteRecoveryGateway())


def _database_path() -> Path:
    return Path(get_db_path())


def inspect_recovery_integrity() -> dict:
    return _APPLICATION.inspect_installation(_database_path())


def create_recovery_backup() -> RecoveryArtifact:
    db_path = _database_path()
    with TemporaryDirectory(prefix="aqorath-backup-download-") as tmp:
        output = Path(tmp) / "aqorath-backup.aqbackup.zip"
        summary = _APPLICATION.create_backup(db_path, output)
        return RecoveryArtifact(
            filename=f"aqorath-backup-{summary['package_id']}.zip",
            media_type="application/zip",
            content=output.read_bytes(),
            summary=summary,
        )


def create_portable_export() -> RecoveryArtifact:
    db_path = _database_path()
    with TemporaryDirectory(prefix="aqorath-portable-download-") as tmp:
        output = Path(tmp) / "aqorath-portable-export.zip"
        summary = _APPLICATION.create_portable_export(db_path, output)
        return RecoveryArtifact(
            filename=f"aqorath-portable-{summary['export_id']}.zip",
            media_type="application/zip",
            content=output.read_bytes(),
            summary=summary,
        )


def restore_recovery_backup(content: bytes) -> dict:
    if not isinstance(content, bytes) or not content:
        raise ValueError("backup package content is required")
    db_path = _database_path()

    # A live SQLAlchemy pool may keep descriptors for the pre-restore SQLite inode.
    # Dispose it before the atomic database replacement and rebuild it afterwards.
    from . import storage

    engine = storage.get_engine()
    engine.dispose()
    try:
        with TemporaryDirectory(prefix="aqorath-backup-upload-") as tmp:
            package = Path(tmp) / "restore.zip"
            package.write_bytes(content)
            result = _APPLICATION.restore_backup(package, db_path)
    finally:
        # Re-initialize against whichever database survived. If restore failed before
        # replacement this simply reopens the original database.
        storage.init_db(str(db_path))
    return result


__all__ = [
    "inspect_recovery_integrity",
    "create_recovery_backup",
    "create_portable_export",
    "restore_recovery_backup",
]
