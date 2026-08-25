"""
P1D.1: Schema migration, backup, restore, and integrity regression tests.

This module freezes the contract for a future aqorath.migrations module that
will serve as the central authority for database schema evolution.

Current state: aqorath.migrations does not exist.
These tests expect a future API:
  - get_schema_version(db_path) -> int
  - validate_sqlite_integrity(db_path) -> bool
  - create_database_backup(db_path, backup_dir=None) -> dict | path
  - restore_database_backup(backup_path, target_path) -> None
  - migrate_database(db_path) -> dict | report
  - CURRENT_SCHEMA_VERSION: int >= 1

Tests are behavioral: they specify outcomes, not implementations.
"""

import pytest
import sqlite3
import os
from pathlib import Path
from decimal import Decimal
from sqlmodel import Session
import aqorath.core as core
from aqorath.models import Account
from aqorath.money import to_decimal_exact


def require_migration_api(*function_names):
    """
    Load aqorath.migrations module and required functions.

    If module doesn't exist or functions missing: pytest.fail gracefully.
    No ImportError during test collection.
    """
    try:
        import aqorath.migrations as migrations
    except ImportError:
        pytest.fail("aqorath.migrations module not implemented")

    functions = {}
    for name in function_names:
        fn = getattr(migrations, name, None)
        if fn is None:
            pytest.fail(f"aqorath.migrations.{name} not implemented")
        functions[name] = fn

    # Also get CURRENT_SCHEMA_VERSION
    version = getattr(migrations, "CURRENT_SCHEMA_VERSION", None)
    if version is None:
        pytest.fail("aqorath.migrations.CURRENT_SCHEMA_VERSION not defined")

    functions["CURRENT_SCHEMA_VERSION"] = version

    return functions


def _create_legacy_float_database(db_path):
    """
    Create a legacy SQLite database with REAL/FLOAT money columns.

    Represents historical Aqorath DBs before TEXT-based money representation.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # Create minimal legacy schema
        conn.execute("""
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                code VARCHAR UNIQUE NOT NULL,
                name VARCHAR NOT NULL,
                nature VARCHAR NOT NULL,
                vat_flag BOOLEAN DEFAULT 0,
                created_at DATETIME
            )
        """)

        conn.execute("""
            CREATE TABLE journalentry (
                id INTEGER PRIMARY KEY,
                date DATETIME,
                concept VARCHAR,
                doc_ref VARCHAR,
                period_id INTEGER,
                posted_by VARCHAR,
                state VARCHAR DEFAULT 'draft',
                created_at DATETIME
            )
        """)

        conn.execute("""
            CREATE TABLE journalline (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER,
                account_code VARCHAR,
                account_id INTEGER,
                debit REAL DEFAULT 0.0,
                credit REAL DEFAULT 0.0,
                description VARCHAR,
                created_at DATETIME
            )
        """)

        # Insert test data
        conn.execute(
            "INSERT INTO account (code, name, nature) VALUES (?, ?, ?)",
            ("1101", "Bancos", "Deudora")
        )
        conn.execute(
            "INSERT INTO account (code, name, nature) VALUES (?, ?, ?)",
            ("4101", "Ventas al contado", "Acreedora")
        )

        conn.execute(
            "INSERT INTO journalentry (id, date, concept) VALUES (?, ?, ?)",
            (1, "2025-01-15", "Depósito bancario")
        )

        # Insert JournalLine with REAL floats
        conn.execute(
            "INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 1, "1101", 1, 0.1, 0.0, "Banco")
        )
        conn.execute(
            "INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (2, 1, "4101", 2, 0.0, 0.1, "Venta")
        )

        # Additional entries to test money precision
        conn.execute(
            "INSERT INTO journalentry (id, date, concept) VALUES (?, ?, ?)",
            (2, "2025-01-16", "Venta adicional")
        )

        conn.execute(
            "INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (3, 2, "1101", 1, 0.2, 0.0, "Depósito adicional")
        )
        conn.execute(
            "INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (4, 2, "4101", 2, 0.0, 0.2, "Venta grande")
        )

        # Large entry
        conn.execute(
            "INSERT INTO journalentry (id, date, concept) VALUES (?, ?, ?)",
            (3, "2025-01-17", "Inversión")
        )

        conn.execute(
            "INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (5, 3, "1101", 1, 1000.0, 0.0, "Depósito grande")
        )

        conn.commit()
    finally:
        conn.close()


# ============================================================
# Schema Version tests
# ============================================================

def test_unversioned_database_reports_schema_zero(tmp_path):
    """
    P1D.1: Database without PRAGMA user_version reports schema version 0.

    Represents truly legacy/unversioned DBs.
    """
    api = require_migration_api("get_schema_version")

    db_file = tmp_path / "unversioned.db"

    # Create minimal SQLite (don't set user_version)
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE dummy (id INTEGER)")
    conn.commit()
    conn.close()

    # Verify it has no user_version set (should default to 0)
    conn = sqlite3.connect(str(db_file))
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()

    assert version == 0, "Unset PRAGMA user_version should be 0"

    # API must report same
    assert api["get_schema_version"](str(db_file)) == 0


def test_new_database_is_initialized_at_current_schema_version(tmp_path):
    """
    P1D.1: Fresh database initialized via migrate_database reaches CURRENT_SCHEMA_VERSION.
    """
    api = require_migration_api(
        "get_schema_version",
        "migrate_database",
        "CURRENT_SCHEMA_VERSION"
    )

    db_file = tmp_path / "new.db"

    # Path doesn't exist yet
    assert not db_file.exists()

    # Migrate (should create it)
    result = api["migrate_database"](str(db_file))

    # Verify file exists
    assert db_file.exists(), "Database file should exist after migration"

    # Verify schema version
    schema_version = api["get_schema_version"](str(db_file))
    assert schema_version == api["CURRENT_SCHEMA_VERSION"], (
        f"New DB schema version {schema_version} must equal CURRENT_SCHEMA_VERSION {api['CURRENT_SCHEMA_VERSION']}"
    )

    # Verify it's a valid SQLite
    assert api["CURRENT_SCHEMA_VERSION"] >= 1, "CURRENT_SCHEMA_VERSION must be >= 1"


# ============================================================
# Legacy Money Format Migration tests
# ============================================================

def test_legacy_float_money_schema_migrates_to_exact_text(tmp_path):
    """
    P1D.1: Legacy REAL/FLOAT columns in journalline migrate to TEXT.

    Ensures future migration converts:
      debit REAL → debit TEXT
      credit REAL → credit TEXT
    """
    api = require_migration_api("migrate_database")

    db_file = tmp_path / "legacy_money.db"
    _create_legacy_float_database(db_file)

    # Before: verify REAL/FLOAT type
    conn = sqlite3.connect(str(db_file))
    schema = conn.execute("PRAGMA table_info(journalline)").fetchall()
    conn.close()

    before_types = {row[1]: row[2] for row in schema}
    assert before_types["debit"] in ("REAL", "FLOAT"), f"Before migration: debit must be REAL/FLOAT, got {before_types['debit']}"
    assert before_types["credit"] in ("REAL", "FLOAT"), f"Before migration: credit must be REAL/FLOAT, got {before_types['credit']}"

    # Migrate
    api["migrate_database"](str(db_file))

    # After: verify TEXT type
    conn = sqlite3.connect(str(db_file))
    schema = conn.execute("PRAGMA table_info(journalline)").fetchall()
    conn.close()

    after_types = {row[1]: row[2] for row in schema}
    assert after_types["debit"] == "TEXT", f"After migration: debit must be TEXT, got {after_types['debit']}"
    assert after_types["credit"] == "TEXT", f"After migration: credit must be TEXT, got {after_types['credit']}"


def test_money_migration_preserves_debit_credit_values(tmp_path):
    """
    P1D.1: Money values are preserved during REAL/FLOAT → TEXT migration.

    Legacy values are normalized to Decimal representation.
    """
    api = require_migration_api("migrate_database")

    db_file = tmp_path / "money_values.db"
    _create_legacy_float_database(db_file)

    # Read legacy REAL values
    conn = sqlite3.connect(str(db_file))
    before_lines = conn.execute(
        "SELECT id, debit, credit FROM journalline ORDER BY id"
    ).fetchall()
    conn.close()

    before_values = {}
    for line_id, debit, credit in before_lines:
        # Normalize legacy float to Decimal using our rule
        before_values[line_id] = {
            "debit": to_decimal_exact(Decimal(str(debit))) if debit else Decimal("0"),
            "credit": to_decimal_exact(Decimal(str(credit))) if credit else Decimal("0"),
        }

    # Migrate
    api["migrate_database"](str(db_file))

    # Read migrated TEXT values
    conn = sqlite3.connect(str(db_file))
    after_lines = conn.execute(
        "SELECT id, debit, credit FROM journalline ORDER BY id"
    ).fetchall()
    conn.close()

    after_values = {}
    for line_id, debit_text, credit_text in after_lines:
        # Parse TEXT as Decimal
        after_values[line_id] = {
            "debit": Decimal(debit_text) if debit_text and debit_text != "0" else Decimal("0"),
            "credit": Decimal(credit_text) if credit_text and credit_text != "0" else Decimal("0"),
        }

    # Compare
    for line_id in before_values:
        assert line_id in after_values, f"Line {line_id} must exist after migration"
        assert after_values[line_id]["debit"] == before_values[line_id]["debit"], (
            f"Line {line_id} debit mismatch: before={before_values[line_id]['debit']}, "
            f"after={after_values[line_id]['debit']}"
        )
        assert after_values[line_id]["credit"] == before_values[line_id]["credit"], (
            f"Line {line_id} credit mismatch: before={before_values[line_id]['credit']}, "
            f"after={after_values[line_id]['credit']}"
        )


def test_money_migration_preserves_journal_line_identity_and_metadata(tmp_path):
    """
    P1D.1: JournalLine row identity and metadata preserved during migration.

    id, entry_id, account_code, account_id, description, created_at must not change.
    """
    api = require_migration_api("migrate_database")

    db_file = tmp_path / "line_identity.db"
    _create_legacy_float_database(db_file)

    # Before
    conn = sqlite3.connect(str(db_file))
    before_lines = conn.execute(
        """SELECT id, entry_id, account_code, account_id, description, created_at
           FROM journalline ORDER BY id"""
    ).fetchall()
    before_count = len(before_lines)
    conn.close()

    # Migrate
    api["migrate_database"](str(db_file))

    # After
    conn = sqlite3.connect(str(db_file))
    after_lines = conn.execute(
        """SELECT id, entry_id, account_code, account_id, description, created_at
           FROM journalline ORDER BY id"""
    ).fetchall()
    after_count = len(after_lines)
    conn.close()

    # Compare
    assert after_count == before_count, f"Row count mismatch: before={before_count}, after={after_count}"

    for before, after in zip(before_lines, after_lines):
        assert before == after, (
            f"JournalLine identity changed: before={before}, after={after}"
        )


# ============================================================
# Backup tests
# ============================================================

def _extract_backup_path(result):
    """
    Extract backup path from various possible result formats.

    Accepts: str, Path, dict, or object with backup_path attribute.
    """
    if isinstance(result, (str, Path)):
        return Path(result)
    if isinstance(result, dict):
        backup_path = result.get("backup_path") or result.get("path")
        if backup_path:
            return Path(backup_path)
    if hasattr(result, "backup_path"):
        return Path(result.backup_path)

    pytest.fail(f"Cannot extract backup path from result: {result!r}")


def test_migration_creates_backup_before_schema_change(tmp_path):
    """
    P1D.1: Backup is created before migration.

    The backup should preserve the pre-migration schema (REAL/FLOAT money).
    """
    api = require_migration_api("migrate_database", "get_schema_version")

    db_file = tmp_path / "backup_test.db"
    _create_legacy_float_database(db_file)

    # Capture original data
    conn = sqlite3.connect(str(db_file))
    original_jl_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    conn.close()

    # Migrate (should create backup)
    result = api["migrate_database"](str(db_file))

    backup_path = _extract_backup_path(result)
    assert backup_path.exists(), f"Backup file must exist: {backup_path}"
    assert backup_path != db_file, "Backup must be separate from target"

    # Verify backup is valid SQLite
    conn = sqlite3.connect(str(backup_path))
    try:
        jl_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
        assert jl_count == original_jl_count, (
            f"Backup must contain original data: expected {original_jl_count}, got {jl_count}"
        )
    finally:
        conn.close()

    # Verify backup has legacy schema (REAL/FLOAT)
    conn = sqlite3.connect(str(backup_path))
    schema = conn.execute("PRAGMA table_info(journalline)").fetchall()
    conn.close()

    types = {row[1]: row[2] for row in schema}
    assert types["debit"] in ("REAL", "FLOAT"), f"Backup debit must be REAL/FLOAT, got {types['debit']}"
    assert types["credit"] in ("REAL", "FLOAT"), f"Backup credit must be REAL/FLOAT, got {types['credit']}"

    # Verify backup has schema version 0 (pre-migration)
    conn = sqlite3.connect(str(backup_path))
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()

    assert version == 0, f"Backup should have user_version=0, got {version}"


def test_backup_is_sqlite_consistent_snapshot(tmp_path):
    """
    P1D.1: Backup passes SQLite integrity check and preserves data counts.
    """
    api = require_migration_api("create_database_backup", "validate_sqlite_integrity")

    db_file = tmp_path / "integrity_test.db"
    _create_legacy_float_database(db_file)

    # Capture original counts
    conn = sqlite3.connect(str(db_file))
    original_account_count = conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    original_entry_count = conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]
    original_line_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    conn.close()

    # Create backup
    result = api["create_database_backup"](str(db_file))

    backup_path = _extract_backup_path(result)
    assert backup_path.exists()

    # Validate integrity
    is_valid = api["validate_sqlite_integrity"](str(backup_path))
    assert is_valid is True or is_valid == "ok", (
        f"Backup must pass integrity check, got: {is_valid!r}"
    )

    # Verify backup preserves data counts
    conn = sqlite3.connect(str(backup_path))
    backup_account_count = conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    backup_entry_count = conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]
    backup_line_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    conn.close()

    assert backup_account_count == original_account_count, (
        f"Backup account count mismatch: {backup_account_count} != {original_account_count}"
    )
    assert backup_entry_count == original_entry_count, (
        f"Backup entry count mismatch: {backup_entry_count} != {original_entry_count}"
    )
    assert backup_line_count == original_line_count, (
        f"Backup line count mismatch: {backup_line_count} != {original_line_count}"
    )


# ============================================================
# Restore tests
# ============================================================

def test_restore_replaces_target_with_backup_state(tmp_path):
    """
    P1D.1: Restore replaces target DB with backup state.
    """
    api = require_migration_api(
        "create_database_backup",
        "restore_database_backup"
    )

    db_file = tmp_path / "restore_test.db"
    _create_legacy_float_database(db_file)

    # Get original data
    conn = sqlite3.connect(str(db_file))
    original_jl_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    original_1101_name = conn.execute("SELECT name FROM account WHERE code = '1101'").fetchone()[0]
    conn.close()

    # Create backup
    result = api["create_database_backup"](str(db_file))

    backup_path = _extract_backup_path(result)

    # Modify target
    conn = sqlite3.connect(str(db_file))
    conn.execute("INSERT INTO journalline (id, entry_id, account_code) VALUES (?, ?, ?)", (999, 999, "9999"))
    conn.execute("UPDATE account SET name = 'Modified' WHERE code = '1101'")
    conn.commit()
    conn.close()

    # Verify modification
    conn = sqlite3.connect(str(db_file))
    modified_jl_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    modified_1101_name = conn.execute("SELECT name FROM account WHERE code = '1101'").fetchone()[0]
    conn.close()

    assert modified_jl_count == original_jl_count + 1, "Modification should add row"
    assert modified_1101_name == "Modified", "Modification should change name"

    # Restore
    api["restore_database_backup"](str(backup_path), str(db_file))

    # Verify restored state
    conn = sqlite3.connect(str(db_file))
    restored_jl_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    restored_1101_name = conn.execute("SELECT name FROM account WHERE code = '1101'").fetchone()[0]

    # Check integrity
    integrity_result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()

    assert restored_jl_count == original_jl_count, (
        f"After restore: count should be {original_jl_count}, got {restored_jl_count}"
    )
    assert restored_1101_name == original_1101_name, (
        f"After restore: name should be '{original_1101_name}', got {restored_1101_name}"
    )
    assert integrity_result == "ok", (
        f"Restored DB must pass integrity_check, got: {integrity_result!r}"
    )


def test_restore_rejects_corrupt_backup(tmp_path):
    """
    P1D.1: Restore validates backup before replacing target.

    Corrupt backup must not replace target.
    """
    api = require_migration_api("restore_database_backup")

    db_file = tmp_path / "target.db"
    _create_legacy_float_database(db_file)

    # Capture original state
    conn = sqlite3.connect(str(db_file))
    original_jl_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    original_1101_name = conn.execute("SELECT name FROM account WHERE code = '1101'").fetchone()[0]
    conn.close()

    corrupt_backup = tmp_path / "corrupt.db"
    corrupt_backup.write_bytes(b"not a sqlite database")

    # Attempt restore with corrupt backup
    with pytest.raises((RuntimeError, ValueError)):
        api["restore_database_backup"](str(corrupt_backup), str(db_file))

    # Verify target is still intact (not modified by failed restore)
    conn = sqlite3.connect(str(db_file))
    final_jl_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    final_1101_name = conn.execute("SELECT name FROM account WHERE code = '1101'").fetchone()[0]
    conn.close()

    assert final_jl_count == original_jl_count, (
        f"Target JournalLine count should be unchanged after failed restore"
    )
    assert final_1101_name == original_1101_name, (
        f"Target 1101 name should be unchanged after failed restore"
    )


# ============================================================
# Integrity tests
# ============================================================

def test_validate_sqlite_integrity_accepts_valid_database(tmp_path):
    """
    P1D.1: validate_sqlite_integrity returns True for valid DB.
    """
    api = require_migration_api("validate_sqlite_integrity")

    db_file = tmp_path / "valid.db"
    _create_legacy_float_database(db_file)

    result = api["validate_sqlite_integrity"](str(db_file))

    # Accept True, "ok", or similar affirmative result
    assert result is True or result == "ok", (
        f"Valid DB should pass, got: {result}"
    )


def test_validate_sqlite_integrity_rejects_corrupt_database(tmp_path):
    """
    P1D.1: validate_sqlite_integrity returns False for corrupt DB.

    No ambiguity: corrupt DB must fail explicitly.
    """
    api = require_migration_api("validate_sqlite_integrity")

    db_file = tmp_path / "corrupt.db"
    db_file.write_bytes(b"not a sqlite database")

    try:
        result = api["validate_sqlite_integrity"](str(db_file))
        # If no exception, result must be explicitly False
        assert result is False, (
            f"Corrupt DB must return False, got: {result!r}"
        )
    except (RuntimeError, ValueError, sqlite3.DatabaseError):
        # Exception is also acceptable
        pass


# ============================================================
# Idempotence tests
# ============================================================

def test_migrate_current_database_is_idempotent(tmp_path):
    """
    P1D.1: Running migrate_database twice is safe.

    Second migration should not duplicate or lose data.
    """
    api = require_migration_api(
        "migrate_database",
        "get_schema_version",
        "CURRENT_SCHEMA_VERSION"
    )

    db_file = tmp_path / "idempotent.db"

    # Create legacy DB first
    _create_legacy_float_database(db_file)

    # First migration
    api["migrate_database"](str(db_file))

    conn = sqlite3.connect(str(db_file))
    version_1 = api["get_schema_version"](str(db_file))
    account_count_1 = conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    entry_count_1 = conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]
    line_count_1 = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]

    # Capture all JournalLine rows
    lines_1 = conn.execute(
        "SELECT id, entry_id, account_code, account_id, debit, credit, description FROM journalline ORDER BY id"
    ).fetchall()

    conn.close()

    # Second migration
    api["migrate_database"](str(db_file))

    conn = sqlite3.connect(str(db_file))
    version_2 = api["get_schema_version"](str(db_file))
    account_count_2 = conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    entry_count_2 = conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]
    line_count_2 = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]

    # Capture all JournalLine rows after second migration
    lines_2 = conn.execute(
        "SELECT id, entry_id, account_code, account_id, debit, credit, description FROM journalline ORDER BY id"
    ).fetchall()

    conn.close()

    # Verify nothing changed
    assert version_2 == version_1, (
        f"Schema version should not change: {version_1} → {version_2}"
    )
    assert version_1 == api["CURRENT_SCHEMA_VERSION"], (
        f"After migration: version should be {api['CURRENT_SCHEMA_VERSION']}, got {version_1}"
    )

    assert account_count_2 == account_count_1, (
        f"Account count should not change: {account_count_1} → {account_count_2}"
    )
    assert entry_count_2 == entry_count_1, (
        f"Entry count should not change: {entry_count_1} → {entry_count_2}"
    )
    assert line_count_2 == line_count_1, (
        f"Line count should not change: {line_count_1} → {line_count_2}"
    )

    assert lines_2 == lines_1, (
        "JournalLine rows must be identical after idempotent migration"
    )


def test_database_newer_than_application_is_rejected(tmp_path):
    """
    P1D.1: Database with schema version > CURRENT_SCHEMA_VERSION is rejected.

    Aqorath should not attempt downgrade or reinterpretation.
    DB must remain unchanged.
    """
    api = require_migration_api(
        "migrate_database",
        "get_schema_version",
        "CURRENT_SCHEMA_VERSION"
    )

    db_file = tmp_path / "newer.db"

    # Create DB with version = CURRENT + 1
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE dummy (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO dummy (id, value) VALUES (1, 'test')")
    conn.execute(f"PRAGMA user_version = {api['CURRENT_SCHEMA_VERSION'] + 1}")
    conn.commit()
    conn.close()

    # Verify initial state
    before_version = api["get_schema_version"](str(db_file))
    conn = sqlite3.connect(str(db_file))
    before_value = conn.execute("SELECT value FROM dummy WHERE id = 1").fetchone()[0]
    conn.close()

    assert before_version == api["CURRENT_SCHEMA_VERSION"] + 1

    # Attempt migration (should fail)
    with pytest.raises((RuntimeError, ValueError)):
        api["migrate_database"](str(db_file))

    # Verify DB is unchanged
    after_version = api["get_schema_version"](str(db_file))
    conn = sqlite3.connect(str(db_file))
    after_value = conn.execute("SELECT value FROM dummy WHERE id = 1").fetchone()[0]
    conn.close()

    assert after_version == before_version, (
        f"Schema version should not change: {before_version} → {after_version}"
    )
    assert after_value == before_value, (
        f"Database data should not change: {before_value} → {after_value}"
    )


# ============================================================
# Failed migration tests
# ============================================================

def require_migrations_module():
    """
    Load aqorath.migrations module and verify MIGRATIONS registry exists.

    This is the future contract: a patchable MIGRATIONS dict.
    """
    try:
        import aqorath.migrations as migrations
    except ImportError:
        pytest.fail("aqorath.migrations module not implemented")

    if not hasattr(migrations, "MIGRATIONS"):
        pytest.fail("aqorath.migrations.MIGRATIONS registry not implemented")

    return migrations


def forced_failure(*args, **kwargs):
    """Migration function that always fails."""
    raise RuntimeError("forced migration failure for testing")


def test_failed_migration_does_not_advance_schema_version(tmp_path, monkeypatch):
    """
    P1D.1B: Failed migration does not advance schema version.

    Uses monkeypatched MIGRATIONS registry to force failure on NEXT pending step.
    Demonstrates: version N → N (no change on failure).
    """
    api = require_migration_api("migrate_database", "get_schema_version")

    migrations = require_migrations_module()

    db_file = tmp_path / "failed_migration.db"
    _create_legacy_float_database(db_file)

    # Get current version and target next version
    before_version = api["get_schema_version"](str(db_file))
    assert before_version == 0, "Unversioned DB must start at 0"

    target_version = before_version + 1
    assert target_version in migrations.MIGRATIONS, (
        f"MIGRATIONS must contain migration to version {target_version}"
    )

    # Monkeypatch migration to fail
    original_migration = migrations.MIGRATIONS.get(target_version)

    monkeypatch.setitem(migrations.MIGRATIONS, target_version, forced_failure)

    try:
        # Attempt migration (should fail)
        with pytest.raises(RuntimeError) as exc_info:
            api["migrate_database"](str(db_file))

        assert "forced migration failure" in str(exc_info.value)
    finally:
        # Restore original
        if original_migration is not None:
            monkeypatch.setitem(migrations.MIGRATIONS, target_version, original_migration)
        else:
            monkeypatch.delitem(migrations.MIGRATIONS, target_version, raising=False)

    # Verify DB version unchanged after failed migration
    after_version = api["get_schema_version"](str(db_file))
    assert after_version == before_version, (
        f"Schema version should not change after failed migration: "
        f"before={before_version}, after={after_version}"
    )


def test_failed_migration_leaves_recoverable_backup(tmp_path, monkeypatch):
    """
    P1D.1B: Failed migration preserves pre-migration backup.

    Proves: backup is created BEFORE migration step begins.
    Migration failure leaves backup in consistent state.
    """
    api = require_migration_api(
        "migrate_database",
        "create_database_backup",
        "get_schema_version"
    )

    migrations = require_migrations_module()

    db_file = tmp_path / "failed_backup_test.db"
    _create_legacy_float_database(db_file)

    # Capture original data and version
    conn = sqlite3.connect(str(db_file))
    original_account_count = conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    original_entry_count = conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]
    original_line_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    original_version = api["get_schema_version"](str(db_file))
    conn.close()

    # Get target version for next step
    target_version = original_version + 1

    assert target_version in migrations.MIGRATIONS, (
        f"MIGRATIONS must contain migration to version {target_version}"
    )

    # Track backup calls
    captured_backup_paths = []
    real_create_backup = api["create_database_backup"]

    def tracked_backup(db_path, backup_dir=None):
        result = real_create_backup(db_path, backup_dir=backup_dir)
        backup_path = _extract_backup_path(result)
        captured_backup_paths.append(backup_path)
        return result

    # Create failure function that verifies backup exists BEFORE it runs
    def forced_failure_after_backup(*args, **kwargs):
        assert captured_backup_paths, (
            "Migration step executed before pre-migration backup"
        )
        backup_path = captured_backup_paths[0]
        assert backup_path.exists(), (
            "Pre-migration backup must physically exist before migration step starts"
        )
        raise RuntimeError("forced migration failure")

    # Monkeypatch backup tracking and migration failure
    monkeypatch.setattr(migrations, "create_database_backup", tracked_backup)

    original_migration = migrations.MIGRATIONS.get(target_version)
    monkeypatch.setitem(migrations.MIGRATIONS, target_version, forced_failure_after_backup)

    try:
        # Attempt migration (should fail)
        with pytest.raises(RuntimeError):
            api["migrate_database"](str(db_file))
    finally:
        # Restore originals
        monkeypatch.setattr(migrations, "create_database_backup", real_create_backup)
        if original_migration is not None:
            monkeypatch.setitem(migrations.MIGRATIONS, target_version, original_migration)
        else:
            monkeypatch.delitem(migrations.MIGRATIONS, target_version, raising=False)

    # Verify backup was created and exists
    assert len(captured_backup_paths) >= 1, (
        "Pre-migration backup must have been created before migration failed"
    )

    backup_path = captured_backup_paths[0]
    assert backup_path.exists(), f"Backup must exist: {backup_path}"

    # Verify backup preserves ALL original data counts
    conn = sqlite3.connect(str(backup_path))
    backup_account_count = conn.execute("SELECT COUNT(*) FROM account").fetchone()[0]
    backup_entry_count = conn.execute("SELECT COUNT(*) FROM journalentry").fetchone()[0]
    backup_line_count = conn.execute("SELECT COUNT(*) FROM journalline").fetchone()[0]
    backup_version = conn.execute("PRAGMA user_version").fetchone()[0]
    integrity_result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()

    assert backup_account_count == original_account_count, (
        f"Backup should preserve account count: {backup_account_count} != {original_account_count}"
    )
    assert backup_entry_count == original_entry_count, (
        f"Backup should preserve entry count: {backup_entry_count} != {original_entry_count}"
    )
    assert backup_line_count == original_line_count, (
        f"Backup should preserve line count: {backup_line_count} != {original_line_count}"
    )
    assert backup_version == original_version, (
        f"Backup should preserve pre-migration version: {backup_version} != {original_version}"
    )
    assert integrity_result == "ok", (
        f"Backup must pass integrity_check, got: {integrity_result!r}"
    )


# ============================================================
# General path migration tests
# ============================================================

def test_unversioned_pre_p1_3_account_schema_migrates_through_general_path(tmp_path):
    """
    P1D.1: Legacy Account schema (no origin/parent_id) migrates via general path.

    Not through ad-hoc _migrate_account_extension_schema in storage.py.
    Eventually, all schema evolution should go through aqorath.migrations.
    """
    api = require_migration_api(
        "migrate_database",
        "get_schema_version",
        "CURRENT_SCHEMA_VERSION"
    )

    db_file = tmp_path / "legacy_account.db"

    # Create legacy Account (pre-P1-3, no origin/parent_id)
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE account (
            id INTEGER PRIMARY KEY,
            code VARCHAR UNIQUE,
            name VARCHAR NOT NULL,
            nature VARCHAR NOT NULL,
            vat_flag BOOLEAN DEFAULT 0,
            created_at DATETIME
        )
    """)
    conn.execute("INSERT INTO account (code, name, nature) VALUES (?, ?, ?)", ("1101", "Bancos", "Deudora"))
    conn.execute("INSERT INTO account (code, name, nature) VALUES (?, ?, ?)", ("4101", "Ventas", "Acreedora"))
    conn.commit()
    conn.close()

    # Before: verify no origin/parent_id
    from sqlalchemy import inspect, create_engine
    engine = create_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    columns_before = {c["name"] for c in insp.get_columns("account")}

    assert "origin" not in columns_before, "Legacy DB should not have origin column"
    assert "parent_id" not in columns_before, "Legacy DB should not have parent_id column"

    # Migrate via general path
    api["migrate_database"](str(db_file))

    # After: verify schema upgraded
    engine = create_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)
    columns_after = {c["name"] for c in insp.get_columns("account")}

    assert "origin" in columns_after, "Migrated DB must have origin column"
    assert "parent_id" in columns_after, "Migrated DB must have parent_id column"

    # Verify data integrity and defaults
    conn = sqlite3.connect(str(db_file))
    account_1101 = conn.execute(
        "SELECT code, name, nature, origin, parent_id FROM account WHERE code = '1101'"
    ).fetchone()

    assert account_1101[0] == "1101", "Code must be preserved"
    assert account_1101[1] == "Bancos", "Name must be preserved"
    assert account_1101[2] == "Deudora", "Nature must be preserved"
    assert account_1101[3] == "canonical", "Origin must default to canonical"
    assert account_1101[4] is None, "Parent_id must be None for canonical"

    # Verify schema version
    version = api["get_schema_version"](str(db_file))
    assert version == api["CURRENT_SCHEMA_VERSION"], (
        f"Schema version must be {api['CURRENT_SCHEMA_VERSION']}, got {version}"
    )

    conn.close()


def test_fresh_database_created_by_general_migration_path_has_current_schema(tmp_path):
    """
    P1D.1: Database created from scratch has current schema.

    All required columns present, schema version correct, data types correct.
    """
    api = require_migration_api(
        "migrate_database",
        "get_schema_version",
        "validate_sqlite_integrity",
        "CURRENT_SCHEMA_VERSION"
    )

    db_file = tmp_path / "fresh.db"
    assert not db_file.exists()

    # Migrate (creates fresh DB)
    api["migrate_database"](str(db_file))

    # Verify file exists and is valid
    assert db_file.exists()
    assert api["validate_sqlite_integrity"](str(db_file)) is True or api["validate_sqlite_integrity"](str(db_file)) == "ok"

    # Verify schema version
    schema_version = api["get_schema_version"](str(db_file))
    assert schema_version == api["CURRENT_SCHEMA_VERSION"], (
        f"Fresh DB schema version must be {api['CURRENT_SCHEMA_VERSION']}, got {schema_version}"
    )

    # Verify Account has P1-3 columns
    from sqlalchemy import inspect, create_engine
    engine = create_engine(f"sqlite:///{db_file}")
    insp = inspect(engine)

    # Account columns
    account_columns = {c["name"] for c in insp.get_columns("account")}
    assert "origin" in account_columns, "Account must have origin column"
    assert "parent_id" in account_columns, "Account must have parent_id column"

    # JournalLine columns and types
    jl_columns = {c["name"]: c["type"] for c in insp.get_columns("journalline")}

    assert "debit" in jl_columns, "JournalLine must have debit column"
    assert "credit" in jl_columns, "JournalLine must have credit column"

    # Check that money columns are not REAL or FLOAT
    debit_type = str(jl_columns["debit"]).upper()
    credit_type = str(jl_columns["credit"]).upper()

    assert "REAL" not in debit_type and "FLOAT" not in debit_type, (
        f"debit should not be REAL/FLOAT, got {debit_type}"
    )
    assert "REAL" not in credit_type and "FLOAT" not in credit_type, (
        f"credit should not be REAL/FLOAT, got {credit_type}"
    )

    # Verify DB integrity
    conn = sqlite3.connect(str(db_file))
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()

    assert integrity == "ok", f"Fresh DB must pass integrity_check, got {integrity!r}"
