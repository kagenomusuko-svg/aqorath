"""Framework-neutral presentation controller for AQR-014."""

from . import recovery_runtime as _recovery


class LocalRecoveryController:
    def integrity(self):
        return _recovery.inspect_recovery_integrity()

    def backup(self):
        return _recovery.create_recovery_backup()

    def portable_export(self):
        return _recovery.create_portable_export()

    def restore(self, content: bytes):
        return _recovery.restore_recovery_backup(content)


__all__ = ["LocalRecoveryController"]
