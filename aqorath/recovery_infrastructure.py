"""AQR-014 SQLite recovery and portable-export infrastructure.

SQLite remains the sole runtime persistence authority. ZIP/JSON values produced here
are point-in-time backup or interchange artifacts only; they are never read as an
alternate live store.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from .migrations import (
    CURRENT_SCHEMA_VERSION,
    create_database_backup,
    get_schema_version,
    migrate_database,
    restore_database_backup,
    validate_sqlite_integrity,
)


BACKUP_FORMAT = "aqorath-backup-v1"
PORTABLE_FORMAT = "aqorath-portable-export-v1"
MANIFEST_MEMBER = "manifest.json"
DATABASE_MEMBER = "database/aqorath.db"
MANAGED_DOCUMENT_ROOT = ".aqorath_documents/restored"


class RecoveryIntegrityError(RuntimeError):
    """Raised when AQR-014 cannot prove enough integrity to continue."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(archive: ZipFile, member: str, value) -> None:
    archive.writestr(
        member,
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"),
    )


def _safe_member(member: str) -> str:
    if not isinstance(member, str) or not member:
        raise RecoveryIntegrityError("Archive member name is missing")
    value = PurePosixPath(member)
    if value.is_absolute() or ".." in value.parts:
        raise RecoveryIntegrityError(f"Unsafe archive member: {member}")
    return member


def _quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _foreign_key_violations(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()
    return [
        {"table": row[0], "rowid": row[1], "parent": row[2], "fk_index": row[3]}
        for row in rows
    ]


def _document_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "documentreference"):
            return []
        rows = conn.execute(
            "SELECT id, file_hash, file_path, external_url "
            "FROM documentreference ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _resolve_document_path(db_path: Path, persisted_path: str) -> Path:
    path = Path(persisted_path).expanduser()
    if not path.is_absolute():
        path = db_path.parent / path
    return path.resolve()


def _inspect_documents(db_path: Path) -> list[dict]:
    results = []
    for row in _document_rows(db_path):
        item = {
            "document_reference_id": int(row["id"]),
            "file_path": row["file_path"],
            "external_url": row["external_url"],
            "stored_file_hash": row["file_hash"],
            "local_file_expected": bool(row["file_path"]),
            "exists": None,
            "actual_sha256": None,
            "hash_matches": None,
            "valid": True,
        }
        if row["file_path"]:
            path = _resolve_document_path(db_path, row["file_path"])
            item["resolved_path"] = str(path)
            item["exists"] = path.is_file()
            if not item["exists"]:
                item["valid"] = False
            else:
                actual_hash = _sha256_path(path)
                item["actual_sha256"] = actual_hash
                if row["file_hash"]:
                    item["hash_matches"] = actual_hash.lower() == str(row["file_hash"]).lower()
                    if not item["hash_matches"]:
                        item["valid"] = False
        results.append(item)
    return results


def _require_supported_database(db_path: Path) -> tuple[int, list[dict]]:
    if not db_path.is_file():
        raise RecoveryIntegrityError(f"Database {db_path} does not exist")
    if not validate_sqlite_integrity(str(db_path)):
        raise RecoveryIntegrityError(f"Database {db_path} is corrupt or not valid SQLite")
    version = get_schema_version(str(db_path))
    if version > CURRENT_SCHEMA_VERSION:
        raise RecoveryIntegrityError(
            f"Database schema version {version} is newer than supported "
            f"version {CURRENT_SCHEMA_VERSION}; refusing downgrade"
        )
    violations = _foreign_key_violations(db_path)
    if violations:
        raise RecoveryIntegrityError(
            f"Database has {len(violations)} foreign-key integrity violation(s)"
        )
    return version, violations


def _manifest_document_entries(db_snapshot: Path, source_db: Path, archive: ZipFile) -> list[dict]:
    entries = []
    for row in _document_rows(db_snapshot):
        doc_id = int(row["id"])
        entry = {
            "document_reference_id": doc_id,
            "original_file_path": row["file_path"],
            "external_url": row["external_url"],
            "stored_file_hash": row["file_hash"],
            "archive_member": None,
            "sha256": None,
            "size": None,
        }
        if row["file_path"]:
            source_path = _resolve_document_path(source_db, row["file_path"])
            if not source_path.is_file():
                raise RecoveryIntegrityError(
                    f"DocumentReference {doc_id} points to missing local file {source_path}"
                )
            actual_hash = _sha256_path(source_path)
            if row["file_hash"] and actual_hash.lower() != str(row["file_hash"]).lower():
                raise RecoveryIntegrityError(
                    f"DocumentReference {doc_id} local file hash does not match persisted file_hash"
                )
            member = f"documents/{doc_id}/{source_path.name or 'document.bin'}"
            archive.write(source_path, member, compress_type=ZIP_DEFLATED)
            entry["archive_member"] = member
            entry["sha256"] = actual_hash
            entry["size"] = source_path.stat().st_size
        entries.append(entry)
    return entries


def _load_manifest(archive: ZipFile, expected_format: str) -> dict:
    names = set(archive.namelist())
    for name in names:
        _safe_member(name)
    if MANIFEST_MEMBER not in names:
        raise RecoveryIntegrityError("Backup package has no manifest.json")
    try:
        manifest = json.loads(archive.read(MANIFEST_MEMBER).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryIntegrityError("Backup manifest is not valid UTF-8 JSON") from exc
    if manifest.get("format") != expected_format:
        raise RecoveryIntegrityError(
            f"Unsupported package format {manifest.get('format')!r}; expected {expected_format!r}"
        )
    if not isinstance(manifest.get("documents"), list):
        raise RecoveryIntegrityError("Backup manifest documents must be a list")
    return manifest


def _validate_manifest_documents(db_path: Path, manifest_documents: list[dict]) -> None:
    database_rows = {int(row["id"]): row for row in _document_rows(db_path)}
    manifest_rows = {}
    for item in manifest_documents:
        try:
            doc_id = int(item["document_reference_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RecoveryIntegrityError("Invalid document_reference_id in manifest") from exc
        if doc_id in manifest_rows:
            raise RecoveryIntegrityError(f"Duplicate DocumentReference {doc_id} in manifest")
        manifest_rows[doc_id] = item
    if set(database_rows) != set(manifest_rows):
        raise RecoveryIntegrityError(
            "Backup document manifest does not correspond exactly to persisted DocumentReference rows"
        )
    for doc_id, row in database_rows.items():
        item = manifest_rows[doc_id]
        if item.get("original_file_path") != row["file_path"]:
            raise RecoveryIntegrityError(
                f"DocumentReference {doc_id} file_path differs between database and manifest"
            )
        if item.get("stored_file_hash") != row["file_hash"]:
            raise RecoveryIntegrityError(
                f"DocumentReference {doc_id} file_hash differs between database and manifest"
            )
        if item.get("external_url") != row["external_url"]:
            raise RecoveryIntegrityError(
                f"DocumentReference {doc_id} external_url differs between database and manifest"
            )
        if row["file_path"] and not item.get("archive_member"):
            raise RecoveryIntegrityError(
                f"DocumentReference {doc_id} requires a local file but manifest contains none"
            )
        if not row["file_path"] and item.get("archive_member"):
            raise RecoveryIntegrityError(
                f"DocumentReference {doc_id} has an unexpected local archive member"
            )


def _extract_documents_for_restore(
    archive: ZipFile,
    manifest: dict,
    staged_db: Path,
    target_db: Path,
) -> tuple[Path | None, list[dict]]:
    package_id = str(manifest.get("package_id", ""))
    if not package_id or len(package_id) > 80 or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
        for character in package_id
    ):
        raise RecoveryIntegrityError("Invalid backup package_id")

    local_items = [item for item in manifest["documents"] if item.get("archive_member")]
    if not local_items:
        return None, []

    managed_root = target_db.parent / MANAGED_DOCUMENT_ROOT / package_id
    if managed_root.exists():
        raise RecoveryIntegrityError(
            f"Managed restore directory already exists: {managed_root}"
        )
    managed_root.mkdir(parents=True, exist_ok=False)
    relocations = []
    try:
        conn = sqlite3.connect(str(staged_db))
        try:
            for item in local_items:
                doc_id = int(item["document_reference_id"])
                member = _safe_member(str(item["archive_member"]))
                if member not in archive.namelist():
                    raise RecoveryIntegrityError(
                        f"Archive member for DocumentReference {doc_id} is missing"
                    )
                expected_hash = str(item.get("sha256") or "").lower()
                if len(expected_hash) != 64:
                    raise RecoveryIntegrityError(
                        f"DocumentReference {doc_id} has invalid manifest SHA-256"
                    )
                basename = PurePosixPath(member).name or "document.bin"
                target_file = managed_root / str(doc_id) / basename
                target_file.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, target_file.open("wb") as target:
                    shutil.copyfileobj(source, target)
                actual_hash = _sha256_path(target_file)
                if actual_hash.lower() != expected_hash:
                    raise RecoveryIntegrityError(
                        f"DocumentReference {doc_id} archive payload hash mismatch"
                    )
                persisted_hash = item.get("stored_file_hash")
                if persisted_hash and actual_hash.lower() != str(persisted_hash).lower():
                    raise RecoveryIntegrityError(
                        f"DocumentReference {doc_id} payload no longer matches persisted file_hash"
                    )
                relative_path = target_file.relative_to(target_db.parent).as_posix()
                updated = conn.execute(
                    "UPDATE documentreference SET file_path=? WHERE id=?",
                    (relative_path, doc_id),
                ).rowcount
                if updated != 1:
                    raise RecoveryIntegrityError(
                        f"DocumentReference {doc_id} cannot be relocated in staged database"
                    )
                relocations.append(
                    {
                        "document_reference_id": doc_id,
                        "original_file_path": item.get("original_file_path"),
                        "restored_file_path": relative_path,
                        "sha256": actual_hash,
                    }
                )
            conn.commit()
        finally:
            conn.close()
        return managed_root, relocations
    except Exception:
        shutil.rmtree(managed_root, ignore_errors=True)
        raise


def _sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]


def _encode_cell(value) -> dict:
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bytes):
        return {"type": "blob-base64", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "real", "value": repr(value)}
    return {"type": "text", "value": str(value)}


def _export_relational_snapshot(db_path: Path, archive: ZipFile) -> tuple[dict, dict]:
    conn = sqlite3.connect(str(db_path))
    try:
        tables = _sqlite_tables(conn)
        schema = {"schema_version": get_schema_version(str(db_path)), "tables": {}}
        row_counts = {}
        for table in tables:
            quoted = _quote_identifier(table)
            columns = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
            foreign_keys = conn.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()
            create_sql_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            schema["tables"][table] = {
                "create_sql": None if create_sql_row is None else create_sql_row[0],
                "columns": [
                    {
                        "cid": row[0],
                        "name": row[1],
                        "declared_type": row[2],
                        "not_null": bool(row[3]),
                        "default": row[4],
                        "primary_key_position": row[5],
                    }
                    for row in columns
                ],
                "foreign_keys": [
                    {
                        "id": row[0],
                        "seq": row[1],
                        "table": row[2],
                        "from": row[3],
                        "to": row[4],
                        "on_update": row[5],
                        "on_delete": row[6],
                        "match": row[7],
                    }
                    for row in foreign_keys
                ],
            }
            pk_columns = [row[1] for row in sorted(columns, key=lambda value: value[5]) if row[5]]
            order_sql = ""
            if pk_columns:
                order_sql = " ORDER BY " + ", ".join(_quote_identifier(name) for name in pk_columns)
            rows = conn.execute(f"SELECT * FROM {quoted}{order_sql}").fetchall()
            row_counts[table] = len(rows)
            _write_json(
                archive,
                f"data/{table}.json",
                {
                    "table": table,
                    "columns": [row[1] for row in columns],
                    "rows": [[_encode_cell(value) for value in row] for row in rows],
                },
            )
        _write_json(archive, "schema.json", schema)
        return schema, row_counts
    finally:
        conn.close()


def _journal_reconciliation(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "journalline"):
            return {"available": False}
        rows = conn.execute("SELECT debit, credit FROM journalline").fetchall()
        debit = Decimal("0")
        credit = Decimal("0")
        try:
            for debit_raw, credit_raw in rows:
                debit += Decimal(str(debit_raw))
                credit += Decimal(str(credit_raw))
        except (InvalidOperation, ValueError) as exc:
            raise RecoveryIntegrityError(
                "JournalLine contains a monetary value that cannot be represented exactly as Decimal"
            ) from exc
        entry_count = 0
        if _table_exists(conn, "journalentry"):
            entry_count = int(conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0])
        return {
            "available": True,
            "entry_count": entry_count,
            "line_count": len(rows),
            "debit_total": str(debit),
            "credit_total": str(credit),
            "balanced": debit == credit,
        }
    finally:
        conn.close()


class SqliteRecoveryGateway:
    """Infrastructure implementation composed from the canonical migration authority."""

    def inspect_installation(self, db_path: Path) -> dict:
        db_path = Path(db_path)
        exists = db_path.is_file()
        sqlite_ok = exists and validate_sqlite_integrity(str(db_path))
        schema_version = None
        schema_supported = False
        schema_current = False
        fk_violations = []
        documents = []
        errors = []
        if not exists:
            errors.append(f"Database {db_path} does not exist")
        elif not sqlite_ok:
            errors.append("SQLite integrity_check failed")
        else:
            try:
                schema_version = get_schema_version(str(db_path))
                schema_supported = schema_version <= CURRENT_SCHEMA_VERSION
                schema_current = schema_version == CURRENT_SCHEMA_VERSION
                if not schema_supported:
                    errors.append(
                        f"Schema {schema_version} is newer than supported {CURRENT_SCHEMA_VERSION}"
                    )
                fk_violations = _foreign_key_violations(db_path)
                if fk_violations:
                    errors.append(f"{len(fk_violations)} foreign-key violation(s)")
                documents = _inspect_documents(db_path)
                invalid_documents = [item for item in documents if not item["valid"]]
                if invalid_documents:
                    errors.append(f"{len(invalid_documents)} local document reference(s) failed integrity")
            except Exception as exc:
                errors.append(str(exc))
        return {
            "database_path": str(db_path),
            "exists": exists,
            "sqlite_integrity": bool(sqlite_ok),
            "schema_version": schema_version,
            "current_schema_version": CURRENT_SCHEMA_VERSION,
            "schema_supported": schema_supported,
            "schema_current": schema_current,
            "foreign_key_violations": fk_violations,
            "documents": documents,
            "healthy": bool(sqlite_ok and schema_current and not fk_violations and all(item["valid"] for item in documents)),
            "errors": errors,
        }

    def create_backup(self, db_path: Path, output_path: Path) -> dict:
        db_path = Path(db_path)
        output_path = Path(output_path)
        source_version, _ = _require_supported_database(db_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        package_id = str(uuid4())
        try:
            with TemporaryDirectory(prefix="aqorath-aqr014-backup-") as tmp:
                tmp_path = Path(tmp)
                backup_result = create_database_backup(str(db_path), backup_dir=str(tmp_path))
                snapshot = Path(backup_result["backup_path"])
                snapshot_version, _ = _require_supported_database(snapshot)
                with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
                    archive.write(snapshot, DATABASE_MEMBER, compress_type=ZIP_DEFLATED)
                    documents = _manifest_document_entries(snapshot, db_path, archive)
                    manifest = {
                        "format": BACKUP_FORMAT,
                        "package_id": package_id,
                        "created_at": _now_iso(),
                        "schema_version": snapshot_version,
                        "current_schema_version": CURRENT_SCHEMA_VERSION,
                        "database_member": DATABASE_MEMBER,
                        "database_sha256": _sha256_path(snapshot),
                        "documents": documents,
                        "authority": "SQLite snapshot; manifest and ZIP are backup transport only",
                    }
                    _write_json(archive, MANIFEST_MEMBER, manifest)
        except Exception:
            if output_path.exists():
                output_path.unlink()
            raise
        return {
            "path": str(output_path),
            "format": BACKUP_FORMAT,
            "package_id": package_id,
            "schema_version": source_version,
            "document_count": len(documents),
            "sha256": _sha256_path(output_path),
        }

    def restore_backup(self, package_path: Path, target_db_path: Path) -> dict:
        package_path = Path(package_path)
        target_db_path = Path(target_db_path)
        if not package_path.is_file():
            raise RecoveryIntegrityError(f"Backup package {package_path} does not exist")
        target_db_path.parent.mkdir(parents=True, exist_ok=True)
        managed_root = None
        pre_restore_backup_path = None
        preserved_corrupt_path = None
        try:
            with TemporaryDirectory(prefix="aqorath-aqr014-restore-") as tmp:
                tmp_path = Path(tmp)
                try:
                    archive = ZipFile(package_path, "r")
                except BadZipFile as exc:
                    raise RecoveryIntegrityError("Backup package is not a valid ZIP archive") from exc
                with archive:
                    manifest = _load_manifest(archive, BACKUP_FORMAT)
                    database_member = _safe_member(str(manifest.get("database_member", "")))
                    if database_member != DATABASE_MEMBER or database_member not in archive.namelist():
                        raise RecoveryIntegrityError("Backup database member is missing or unsupported")
                    staged_db = tmp_path / "restore-candidate.db"
                    with archive.open(database_member, "r") as source, staged_db.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    expected_db_hash = str(manifest.get("database_sha256") or "").lower()
                    if _sha256_path(staged_db).lower() != expected_db_hash:
                        raise RecoveryIntegrityError("Backup database SHA-256 does not match manifest")
                    candidate_version, _ = _require_supported_database(staged_db)
                    if candidate_version < CURRENT_SCHEMA_VERSION:
                        migrate_database(str(staged_db))
                    _require_supported_database(staged_db)
                    _validate_manifest_documents(staged_db, manifest["documents"])
                    managed_root, relocations = _extract_documents_for_restore(
                        archive, manifest, staged_db, target_db_path
                    )
                    _require_supported_database(staged_db)

                    if target_db_path.exists():
                        if validate_sqlite_integrity(str(target_db_path)):
                            current_target_version = get_schema_version(str(target_db_path))
                            if current_target_version > CURRENT_SCHEMA_VERSION:
                                raise RecoveryIntegrityError(
                                    f"Installed database schema {current_target_version} is newer than this application; refusing destructive restore"
                                )
                            safety = create_database_backup(
                                str(target_db_path),
                                backup_dir=str(target_db_path.parent / ".aqorath_backups"),
                            )
                            pre_restore_backup_path = safety["backup_path"]
                        else:
                            preserve_dir = target_db_path.parent / ".aqorath_backups"
                            preserve_dir.mkdir(parents=True, exist_ok=True)
                            preserved = preserve_dir / (
                                f"{target_db_path.stem}.corrupt-before-restore.{uuid4()}.db"
                            )
                            shutil.copy2(target_db_path, preserved)
                            preserved_corrupt_path = str(preserved)

                    restore_database_backup(str(staged_db), str(target_db_path))
                    _require_supported_database(target_db_path)
                    restored_documents = _inspect_documents(target_db_path)
                    if any(not item["valid"] for item in restored_documents):
                        raise RecoveryIntegrityError(
                            "Restored database references a local document that failed integrity"
                        )
                    return {
                        "restored": True,
                        "package_id": manifest["package_id"],
                        "source_schema_version": candidate_version,
                        "restored_schema_version": get_schema_version(str(target_db_path)),
                        "pre_restore_backup_path": pre_restore_backup_path,
                        "preserved_corrupt_path": preserved_corrupt_path,
                        "document_relocations": relocations,
                        "database_path": str(target_db_path),
                    }
        except Exception:
            if managed_root is not None:
                shutil.rmtree(managed_root, ignore_errors=True)
            raise

    def create_portable_export(self, db_path: Path, output_path: Path) -> dict:
        db_path = Path(db_path)
        output_path = Path(output_path)
        source_version, _ = _require_supported_database(db_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_id = str(uuid4())
        try:
            with TemporaryDirectory(prefix="aqorath-aqr014-export-") as tmp:
                tmp_path = Path(tmp)
                backup_result = create_database_backup(str(db_path), backup_dir=str(tmp_path))
                snapshot = Path(backup_result["backup_path"])
                _require_supported_database(snapshot)
                with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
                    schema, row_counts = _export_relational_snapshot(snapshot, archive)
                    documents = _manifest_document_entries(snapshot, db_path, archive)
                    reconciliation = _journal_reconciliation(snapshot)
                    _write_json(archive, "reconciliation.json", reconciliation)
                    manifest = {
                        "format": PORTABLE_FORMAT,
                        "export_id": export_id,
                        "created_at": _now_iso(),
                        "schema_version": source_version,
                        "current_schema_version": CURRENT_SCHEMA_VERSION,
                        "encoding": {
                            "rows": "typed JSON cells",
                            "integer": "base-10 text",
                            "real": "Python repr of SQLite REAL",
                            "text": "UTF-8 string; monetary Decimal values remain exact SQLite TEXT",
                            "blob-base64": "RFC 4648 base64",
                            "null": None,
                        },
                        "tables": sorted(schema["tables"]),
                        "row_counts": row_counts,
                        "documents": documents,
                        "reconciliation_member": "reconciliation.json",
                        "schema_member": "schema.json",
                        "authority": "Interchange snapshot only; importing this JSON is not an Aqorath persistence path",
                    }
                    _write_json(archive, MANIFEST_MEMBER, manifest)
        except Exception:
            if output_path.exists():
                output_path.unlink()
            raise
        return {
            "path": str(output_path),
            "format": PORTABLE_FORMAT,
            "export_id": export_id,
            "schema_version": source_version,
            "table_count": len(row_counts),
            "row_counts": row_counts,
            "document_count": len(documents),
            "sha256": _sha256_path(output_path),
        }


__all__ = [
    "BACKUP_FORMAT",
    "PORTABLE_FORMAT",
    "MANIFEST_MEMBER",
    "DATABASE_MEMBER",
    "RecoveryIntegrityError",
    "SqliteRecoveryGateway",
]
