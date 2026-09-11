import hashlib
import json
import sqlite3
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from aqorath.migrations import CURRENT_SCHEMA_VERSION, get_schema_version, migrate_database
from aqorath.recovery_infrastructure import (
    BACKUP_FORMAT,
    DATABASE_MEMBER,
    MANIFEST_MEMBER,
    PORTABLE_FORMAT,
    RecoveryIntegrityError,
    SqliteRecoveryGateway,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_current_database(tmp_path: Path, name="source.db", with_document=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / name
    migrate_database(str(db))
    created = "2026-09-11T12:00:00+00:00"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO entity "
            "(id, name, rfc, legal_personality, legal_form, is_active, created_at) "
            "VALUES (1, 'Entidad AQR-014', 'AAA010101AAA', 'moral', 'ac', 1, ?)",
            (created,),
        )
        conn.execute(
            "INSERT INTO journalentry "
            "(id, date, concept, doc_ref, period_id, posted_by, state, created_at) "
            "VALUES (1, ?, ?, ?, NULL, ?, ?, ?)",
            (created, "AQR-014 fixture", "DOC-1", "test", "posted", created),
        )
        conn.execute(
            "INSERT INTO journalline "
            "(id, entry_id, account_code, account_id, debit, credit, description, created_at) "
            "VALUES (1, 1, '1101', NULL, '1234.50', '0', 'debit', ?)",
            (created,),
        )
        conn.execute(
            "INSERT INTO journalline "
            "(id, entry_id, account_code, account_id, debit, credit, description, created_at) "
            "VALUES (2, 1, '4101', NULL, '0', '1234.50', 'credit', ?)",
            (created,),
        )
        document_path = None
        document_hash = None
        if with_document:
            evidence = tmp_path / "evidence" / "receipt.txt"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_bytes(b"AQR-014 external evidence\n")
            document_path = "evidence/receipt.txt"
            document_hash = _sha256(evidence)
        conn.execute(
            "INSERT INTO documentreference "
            "(id, entry_id, third_party_id, document_type, document_number, issuer_name, date, "
            "file_hash, file_path, external_url, is_validated, validation_notes, created_at) "
            "VALUES (1, 1, NULL, 'receipt', 'DOC-1', 'Fixture', ?, ?, ?, NULL, 1, 'fixture', ?)",
            (created, document_hash, document_path, created),
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _typed_rows(archive: ZipFile, table: str):
    payload = json.loads(archive.read(f"data/{table}.json").decode("utf-8"))
    return payload["columns"], payload["rows"]


def test_backup_restore_clean_install_preserves_ledger_entity_and_external_evidence(tmp_path):
    source_dir = tmp_path / "source"
    source = _make_current_database(source_dir)
    gateway = SqliteRecoveryGateway()
    package = tmp_path / "backup.zip"

    backup = gateway.create_backup(source, package)

    assert backup["format"] == BACKUP_FORMAT
    assert backup["schema_version"] == CURRENT_SCHEMA_VERSION
    assert backup["document_count"] == 1

    clean_dir = tmp_path / "clean-install"
    clean_dir.mkdir()
    restored = clean_dir / "aqorath.db"
    result = gateway.restore_backup(package, restored)

    assert result["restored"] is True
    assert result["source_schema_version"] == CURRENT_SCHEMA_VERSION
    assert get_schema_version(str(restored)) == CURRENT_SCHEMA_VERSION
    assert result["pre_restore_backup_path"] is None

    conn = sqlite3.connect(str(restored))
    try:
        assert conn.execute(
            "SELECT id, name, rfc, legal_personality, legal_form, is_active FROM entity WHERE id=1"
        ).fetchone() == (1, "Entidad AQR-014", "AAA010101AAA", "moral", "ac", 1)
        assert conn.execute(
            "SELECT id, state, concept FROM journalentry WHERE id=1"
        ).fetchone() == (1, "posted", "AQR-014 fixture")
        assert conn.execute(
            "SELECT id, debit, credit FROM journalline ORDER BY id"
        ).fetchall() == [(1, "1234.50", "0"), (2, "0", "1234.50")]
        file_path, file_hash = conn.execute(
            "SELECT file_path, file_hash FROM documentreference WHERE id=1"
        ).fetchone()
    finally:
        conn.close()

    assert file_path.startswith(".aqorath_documents/restored/")
    restored_evidence = clean_dir / file_path
    assert restored_evidence.read_bytes() == b"AQR-014 external evidence\n"
    assert _sha256(restored_evidence) == file_hash
    assert gateway.inspect_installation(restored)["healthy"] is True


def test_restore_over_healthy_installation_creates_pre_restore_backup(tmp_path):
    gateway = SqliteRecoveryGateway()
    source = _make_current_database(tmp_path / "source")
    target = _make_current_database(tmp_path / "target", name="aqorath.db")
    conn = sqlite3.connect(str(target))
    try:
        conn.execute("UPDATE journalentry SET concept='target-before-restore' WHERE id=1")
        conn.commit()
    finally:
        conn.close()
    package = tmp_path / "backup.zip"
    gateway.create_backup(source, package)

    result = gateway.restore_backup(package, target)

    safety = Path(result["pre_restore_backup_path"])
    assert safety.is_file()
    conn = sqlite3.connect(str(safety))
    try:
        assert conn.execute("SELECT concept FROM journalentry WHERE id=1").fetchone()[0] == "target-before-restore"
    finally:
        conn.close()
    conn = sqlite3.connect(str(target))
    try:
        assert conn.execute("SELECT concept FROM journalentry WHERE id=1").fetchone()[0] == "AQR-014 fixture"
    finally:
        conn.close()


def test_restore_rejects_corrupt_package_without_touching_healthy_database(tmp_path):
    target = _make_current_database(tmp_path / "target", name="aqorath.db")
    before = _sha256(target)
    corrupt = tmp_path / "corrupt.zip"
    corrupt.write_bytes(b"not a zip")

    with pytest.raises(RecoveryIntegrityError, match="valid ZIP"):
        SqliteRecoveryGateway().restore_backup(corrupt, target)

    assert _sha256(target) == before
    assert get_schema_version(str(target)) == CURRENT_SCHEMA_VERSION


def test_restore_rejects_future_schema_before_replacing_healthy_database(tmp_path):
    target_dir = tmp_path / "target"
    target = _make_current_database(target_dir, name="aqorath.db", with_document=False)
    before = _sha256(target)

    future = tmp_path / "future.db"
    migrate_database(str(future))
    conn = sqlite3.connect(str(future))
    try:
        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION + 1}")
        conn.commit()
    finally:
        conn.close()

    package = tmp_path / "future-backup.zip"
    manifest = {
        "format": BACKUP_FORMAT,
        "package_id": "future-schema-fixture",
        "created_at": "2026-09-11T12:00:00+00:00",
        "schema_version": CURRENT_SCHEMA_VERSION + 1,
        "current_schema_version": CURRENT_SCHEMA_VERSION,
        "database_member": DATABASE_MEMBER,
        "database_sha256": _sha256(future),
        "documents": [],
    }
    with ZipFile(package, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(future, DATABASE_MEMBER)
        archive.writestr(MANIFEST_MEMBER, json.dumps(manifest).encode("utf-8"))

    with pytest.raises(RecoveryIntegrityError, match="newer than supported"):
        SqliteRecoveryGateway().restore_backup(package, target)

    assert _sha256(target) == before
    assert get_schema_version(str(target)) == CURRENT_SCHEMA_VERSION


def test_backup_stops_when_referenced_local_document_hash_changed(tmp_path):
    source = _make_current_database(tmp_path)
    (tmp_path / "evidence" / "receipt.txt").write_bytes(b"tampered\n")

    with pytest.raises(RecoveryIntegrityError, match="does not match persisted file_hash"):
        SqliteRecoveryGateway().create_backup(source, tmp_path / "backup.zip")

    assert not (tmp_path / "backup.zip").exists()


def test_integrity_detects_relational_breakage(tmp_path):
    db = _make_current_database(tmp_path, with_document=False)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("UPDATE documentreference SET entry_id=999 WHERE id=1")
        conn.commit()
    finally:
        conn.close()

    result = SqliteRecoveryGateway().inspect_installation(db)

    assert result["sqlite_integrity"] is True
    assert result["schema_current"] is True
    assert result["healthy"] is False
    assert result["foreign_key_violations"]
    assert result["foreign_key_violations"][0]["table"] == "documentreference"


def test_portable_export_is_independently_readable_and_relational(tmp_path):
    source = _make_current_database(tmp_path)
    export = tmp_path / "portable.zip"

    summary = SqliteRecoveryGateway().create_portable_export(source, export)

    assert summary["format"] == PORTABLE_FORMAT
    assert summary["schema_version"] == CURRENT_SCHEMA_VERSION
    assert summary["row_counts"]["entity"] == 1
    assert summary["row_counts"]["journalentry"] == 1
    assert summary["row_counts"]["journalline"] == 2
    assert summary["row_counts"]["documentreference"] == 1

    # This read path intentionally imports no Aqorath code: the archive is self-describing.
    with ZipFile(export, "r") as archive:
        manifest = json.loads(archive.read(MANIFEST_MEMBER).decode("utf-8"))
        schema = json.loads(archive.read("schema.json").decode("utf-8"))
        reconciliation = json.loads(archive.read("reconciliation.json").decode("utf-8"))
        line_columns, line_rows = _typed_rows(archive, "journalline")
        doc_columns, doc_rows = _typed_rows(archive, "documentreference")

        assert manifest["format"] == PORTABLE_FORMAT
        assert {"entity", "journalentry", "journalline", "documentreference"} <= set(manifest["tables"])
        assert manifest["encoding"]["text"].startswith("UTF-8")
        assert reconciliation == {
            "available": True,
            "balanced": True,
            "credit_total": "1234.50",
            "debit_total": "1234.50",
            "entry_count": 1,
            "line_count": 2,
        }

        debit_index = line_columns.index("debit")
        credit_index = line_columns.index("credit")
        assert line_rows[0][debit_index] == {"type": "text", "value": "1234.50"}
        assert line_rows[1][credit_index] == {"type": "text", "value": "1234.50"}

        doc_entry_fk = [
            fk for fk in schema["tables"]["documentreference"]["foreign_keys"]
            if fk["from"] == "entry_id"
        ]
        assert doc_entry_fk and doc_entry_fk[0]["table"] == "journalentry"
        doc_id_index = doc_columns.index("id")
        assert doc_rows[0][doc_id_index] == {"type": "integer", "value": "1"}

        local_doc = manifest["documents"][0]
        assert local_doc["document_reference_id"] == 1
        assert local_doc["sha256"] == local_doc["stored_file_hash"]
        assert archive.read(local_doc["archive_member"]) == b"AQR-014 external evidence\n"


def test_recovery_surface_is_part_of_real_local_launcher():
    from aqorath import local_server
    from aqorath.recovery_web import RECOVERY_HTML, app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/recovery" in paths
    assert "/api/system/integrity" in paths
    assert "/api/system/backup" in paths
    assert "/api/system/restore" in paths
    assert "/api/system/portable-export" in paths
    assert "Respaldo, integridad y portabilidad" in RECOVERY_HTML

    import inspect

    source = inspect.getsource(local_server.run_local_surface)
    assert "aqorath.recovery_web:app" in source
