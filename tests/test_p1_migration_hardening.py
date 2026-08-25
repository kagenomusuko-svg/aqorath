"""
P1D.2A: Hardening tests for migration data integrity.

Freezes contracts for:
- Import independence of schema creation
- NULL monetary value rejection
- Extra column rejection
- Structural transaction atomicity
- Asset legacy migration
"""

import os
import pytest
import sqlite3
import subprocess
import sys
from pathlib import Path
from decimal import Decimal

from aqorath.migrations import migrate_database, CURRENT_SCHEMA_VERSION


def test_fresh_migration_does_not_depend_on_prior_model_import(tmp_path):
    """
    P1D.2A: Fresh DB creation is independent of module import order.

    Uses subprocess to ensure models haven't been imported before migrate_database.
    This validates that _create_current_schema() explicitly imports models.
    """
    db_file = tmp_path / "fresh_isolated.db"

    # Calculate repo root dynamically
    repo_root = Path(__file__).resolve().parents[1]

    # Write a subprocess script that migrates without prior model imports
    script = f"""
import sys
from pathlib import Path
from aqorath.migrations import migrate_database, CURRENT_SCHEMA_VERSION
import sqlite3

db = Path({str(db_file)!r})
migrate_database(str(db))

# Verify tables exist
conn = sqlite3.connect(str(db))
tables = {{row[0] for row in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"
).fetchall()}}
conn.close()

expected = {{"account", "journalentry", "journalline", "asset"}}
assert expected.issubset(tables), f"Missing tables: {{expected - tables}}"

# Verify schema version
conn = sqlite3.connect(str(db))
version = conn.execute("PRAGMA user_version").fetchone()[0]
conn.close()

assert version == CURRENT_SCHEMA_VERSION, f"Version mismatch: {{version}} != {{CURRENT_SCHEMA_VERSION}}"
print("OK")
"""

    # Set up environment with dynamic PYTHONPATH
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not existing_pythonpath
        else str(repo_root) + os.pathsep + existing_pythonpath
    )

    # Run subprocess
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Subprocess failed: {result.stderr}"
    assert db_file.exists()


def test_legacy_journalline_null_money_is_rejected(tmp_path):
    """
    P1D.2A: JournalLine with NULL debit or credit is rejected during migration.

    NULL monetary values represent inconsistent state.
    Migration must fail, leaving DB unmodified.
    """
    db_file = tmp_path / "null_money.db"

    # Create legacy DB with NULL debit
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE account (id INTEGER PRIMARY KEY, code VARCHAR, name VARCHAR, nature VARCHAR)
    """)
    conn.execute("""
        CREATE TABLE journalentry (id INTEGER PRIMARY KEY, date DATETIME)
    """)
    conn.execute("""
        CREATE TABLE journalline (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER,
            account_code VARCHAR,
            account_id INTEGER,
            debit REAL,
            credit REAL,
            description VARCHAR,
            created_at DATETIME
        )
    """)

    # Insert entry with NULL debit
    conn.execute("INSERT INTO journalentry (id, date) VALUES (1, '2025-01-15')")
    conn.execute(
        "INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit, description) "
        "VALUES (1, 1, '1101', 1, NULL, 0.0, 'Bad entry')"
    )
    conn.commit()
    conn.close()

    # Verify before
    conn = sqlite3.connect(str(db_file))
    version_before = conn.execute("PRAGMA user_version").fetchone()[0]
    debit_before = conn.execute("SELECT debit FROM journalline WHERE id = 1").fetchone()[0]
    conn.close()

    assert version_before == 0
    assert debit_before is None

    # Attempt migration
    with pytest.raises(RuntimeError) as exc_info:
        migrate_database(str(db_file))

    assert "monetary value" in str(exc_info.value).lower()

    # Verify after: DB unchanged
    conn = sqlite3.connect(str(db_file))
    version_after = conn.execute("PRAGMA user_version").fetchone()[0]
    debit_after = conn.execute("SELECT debit FROM journalline WHERE id = 1").fetchone()[0]
    conn.close()

    assert version_after == 0, "Version should not advance on failed migration"
    assert debit_after is None, "Debit should remain NULL"


def test_legacy_asset_null_value_is_rejected(tmp_path):
    """
    P1D.2A: Asset with NULL value is rejected during migration.
    """
    db_file = tmp_path / "asset_null.db"

    # Create legacy DB with NULL asset value
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE asset (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            value REAL,
            created_at DATETIME
        )
    """)

    conn.execute("INSERT INTO asset (id, name, value) VALUES (1, 'Asset A', NULL)")
    conn.commit()
    conn.close()

    # Verify before
    conn = sqlite3.connect(str(db_file))
    version_before = conn.execute("PRAGMA user_version").fetchone()[0]
    value_before = conn.execute("SELECT value FROM asset WHERE id = 1").fetchone()[0]
    conn.close()

    assert version_before == 0
    assert value_before is None

    # Attempt migration
    with pytest.raises(RuntimeError) as exc_info:
        migrate_database(str(db_file))

    assert "null" in str(exc_info.value).lower() and "value" in str(exc_info.value).lower()

    # Verify after: DB unchanged
    conn = sqlite3.connect(str(db_file))
    version_after = conn.execute("PRAGMA user_version").fetchone()[0]
    value_after = conn.execute("SELECT value FROM asset WHERE id = 1").fetchone()[0]
    conn.close()

    assert version_after == 0
    assert value_after is None


def test_journalline_rebuild_rejects_unpreserved_extra_column(tmp_path):
    """
    P1D.2A: JournalLine with extra unpreserved column is rejected.

    Only supported columns are migrated. Extra columns would be lost silently.
    Migration must fail.
    """
    db_file = tmp_path / "extra_jl_column.db"

    # Create legacy DB with extra column
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE journalline (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER,
            account_code VARCHAR,
            account_id INTEGER,
            debit REAL,
            credit REAL,
            description VARCHAR,
            created_at DATETIME,
            custom_note TEXT
        )
    """)

    conn.execute(
        "INSERT INTO journalline "
        "(id, entry_id, account_code, account_id, debit, credit, description, custom_note) "
        "VALUES (1, 1, '1101', 1, 0.1, 0.0, 'Test', 'NO PERDER')"
    )
    conn.commit()
    conn.close()

    # Verify before
    conn = sqlite3.connect(str(db_file))
    version_before = conn.execute("PRAGMA user_version").fetchone()[0]
    custom_note = conn.execute("SELECT custom_note FROM journalline WHERE id = 1").fetchone()[0]
    conn.close()

    assert version_before == 0
    assert custom_note == "NO PERDER"

    # Attempt migration
    with pytest.raises(RuntimeError) as exc_info:
        migrate_database(str(db_file))

    assert "unknown columns" in str(exc_info.value).lower()

    # Verify after: original table still exists with data
    conn = sqlite3.connect(str(db_file))
    version_after = conn.execute("PRAGMA user_version").fetchone()[0]
    custom_note_after = conn.execute("SELECT custom_note FROM journalline WHERE id = 1").fetchone()[0]
    # Temp table should not exist
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()

    assert version_after == 0
    assert custom_note_after == "NO PERDER", "Custom note must be preserved"
    assert "journalline__aqorath_v1" not in tables, "Temp table should not persist after failure"


def test_asset_rebuild_rejects_unpreserved_extra_column(tmp_path):
    """
    P1D.2A: Asset with extra unpreserved column is rejected.
    """
    db_file = tmp_path / "extra_asset_column.db"

    # Create legacy DB with extra column
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE asset (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            value REAL,
            created_at DATETIME,
            serial_number TEXT
        )
    """)

    conn.execute(
        "INSERT INTO asset (id, name, value, serial_number) VALUES (1, 'Asset A', 0.1, 'ABC-123')"
    )
    conn.commit()
    conn.close()

    # Verify before
    conn = sqlite3.connect(str(db_file))
    version_before = conn.execute("PRAGMA user_version").fetchone()[0]
    serial = conn.execute("SELECT serial_number FROM asset WHERE id = 1").fetchone()[0]
    conn.close()

    assert version_before == 0
    assert serial == "ABC-123"

    # Attempt migration
    with pytest.raises(RuntimeError) as exc_info:
        migrate_database(str(db_file))

    assert "unknown columns" in str(exc_info.value).lower()

    # Verify after
    conn = sqlite3.connect(str(db_file))
    version_after = conn.execute("PRAGMA user_version").fetchone()[0]
    serial_after = conn.execute("SELECT serial_number FROM asset WHERE id = 1").fetchone()[0]
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()

    assert version_after == 0
    assert serial_after == "ABC-123"
    assert "asset__aqorath_v1" not in tables


def test_migration_step_rolls_back_prior_table_changes_if_later_table_fails(tmp_path):
    """
    P1D.2A: Structural changes are atomic within single transaction.

    If a later table (Asset) fails, earlier changes (Account, JournalLine) are rolled back.
    """
    db_file = tmp_path / "rollback_test.db"

    # Create DB with Account (needs migration), JournalLine (needs migration), Asset (will fail)
    conn = sqlite3.connect(str(db_file))

    # Account: no origin/parent_id (needs ALTER)
    conn.execute("""
        CREATE TABLE account (
            id INTEGER PRIMARY KEY,
            code VARCHAR UNIQUE,
            name VARCHAR,
            nature VARCHAR
        )
    """)
    conn.execute("INSERT INTO account (code, name, nature) VALUES ('1101', 'Bancos', 'Deudora')")

    # JournalLine: REAL/FLOAT (needs rebuild)
    conn.execute("""
        CREATE TABLE journalline (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER,
            account_code VARCHAR,
            account_id INTEGER,
            debit REAL,
            credit REAL,
            description VARCHAR,
            created_at DATETIME
        )
    """)
    conn.execute("INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit) "
                 "VALUES (1, 1, '1101', 1, 0.1, 0.0)")

    # Asset: will have NULL value (will fail)
    conn.execute("""
        CREATE TABLE asset (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            value REAL,
            created_at DATETIME
        )
    """)
    conn.execute("INSERT INTO asset (id, name, value) VALUES (1, 'Asset A', NULL)")

    conn.commit()
    conn.close()

    # Verify before
    conn = sqlite3.connect(str(db_file))
    version_before = conn.execute("PRAGMA user_version").fetchone()[0]

    account_cols = {row[1] for row in conn.execute("PRAGMA table_info(account)").fetchall()}
    jl_type_before = [row[2] for row in conn.execute("PRAGMA table_info(journalline)").fetchall()
                      if row[1] == "debit"][0]
    asset_value_before = conn.execute("SELECT value FROM asset WHERE id = 1").fetchone()[0]

    conn.close()

    assert version_before == 0
    assert "origin" not in account_cols, "Account should not have origin yet"
    assert "REAL" in jl_type_before, "JournalLine debit should still be REAL"
    assert asset_value_before is None, "Asset value should be NULL"

    # Attempt migration (should fail on Asset NULL value)
    with pytest.raises(RuntimeError):
        migrate_database(str(db_file))

    # Verify after: rollback occurred
    conn = sqlite3.connect(str(db_file))
    version_after = conn.execute("PRAGMA user_version").fetchone()[0]

    account_cols_after = {row[1] for row in conn.execute("PRAGMA table_info(account)").fetchall()}
    jl_type_after = [row[2] for row in conn.execute("PRAGMA table_info(journalline)").fetchall()
                     if row[1] == "debit"][0]
    asset_value_after = conn.execute("SELECT value FROM asset WHERE id = 1").fetchone()[0]

    conn.close()

    assert version_after == 0, "Version should not advance"
    assert "origin" not in account_cols_after, "Account origin should not exist (rolled back)"
    assert "REAL" in jl_type_after, "JournalLine should still be REAL (rolled back)"
    assert asset_value_after is None, "Asset value should remain NULL"


def test_legacy_asset_real_migrates_to_exact_text(tmp_path):
    """
    P1D.2A: Asset.value REAL/FLOAT → TEXT with exact decimal preservation.
    """
    db_file = tmp_path / "asset_real_migrate.db"

    # Create legacy Asset table
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE asset (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            value REAL,
            created_at DATETIME
        )
    """)

    # Insert test values
    conn.execute("INSERT INTO asset (id, name, value) VALUES (1, 'Activo A', 0.1)")
    conn.execute("INSERT INTO asset (id, name, value) VALUES (2, 'Activo B', 1000.0)")

    conn.commit()
    conn.close()

    # Verify before
    conn = sqlite3.connect(str(db_file))
    value_type_before = [row[2] for row in conn.execute("PRAGMA table_info(asset)").fetchall()
                         if row[1] == "value"][0]
    rows_before = conn.execute("SELECT id, name, value FROM asset ORDER BY id").fetchall()
    conn.close()

    assert "REAL" in value_type_before or "FLOAT" in value_type_before
    assert rows_before == [(1, "Activo A", 0.1), (2, "Activo B", 1000.0)]

    # Migrate
    migrate_database(str(db_file))

    # Verify after
    conn = sqlite3.connect(str(db_file))
    value_type_after = [row[2] for row in conn.execute("PRAGMA table_info(asset)").fetchall()
                        if row[1] == "value"][0]
    rows_after = conn.execute("SELECT id, name, value FROM asset ORDER BY id").fetchall()
    version_after = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()

    assert "REAL" not in value_type_after and "FLOAT" not in value_type_after
    assert value_type_after == "TEXT"

    # Verify decimal values preserved
    assert rows_after[0][:2] == (1, "Activo A"), "ID and name preserved"
    assert Decimal(rows_after[0][2]) == Decimal("0.1"), "0.1 preserved exactly"

    assert rows_after[1][:2] == (2, "Activo B"), "ID and name preserved"
    assert Decimal(rows_after[1][2]) == Decimal("1000.0"), "1000.0 preserved exactly"

    assert version_after == CURRENT_SCHEMA_VERSION


def test_migrated_journalline_money_columns_are_not_nullable(tmp_path):
    """
    P1D.2B: After migration, JournalLine debit/credit are NOT NULL in schema.

    Validates physical constraint prevents future NULL insertion.
    """
    db_file = tmp_path / "jl_not_null.db"

    # Create legacy JournalLine with valid REAL values
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE journalline (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER,
            account_code VARCHAR,
            account_id INTEGER,
            debit REAL,
            credit REAL,
            description VARCHAR,
            created_at DATETIME
        )
    """)
    conn.execute(
        "INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit) "
        "VALUES (1, 1, '1101', 1, 0.1, 0.0)"
    )
    conn.commit()
    conn.close()

    # Migrate
    migrate_database(str(db_file))

    # Verify schema: debit and credit are NOT NULL
    conn = sqlite3.connect(str(db_file))
    table_info = conn.execute("PRAGMA table_info(journalline)").fetchall()
    schema_dict = {row[1]: row for row in table_info}

    debit_row = schema_dict.get("debit")
    credit_row = schema_dict.get("credit")

    assert debit_row is not None, "debit column exists"
    assert credit_row is not None, "credit column exists"

    # notnull column is index 3; 1 = NOT NULL, 0 = nullable
    assert debit_row[3] == 1, f"debit should be NOT NULL, got: {debit_row}"
    assert credit_row[3] == 1, f"credit should be NOT NULL, got: {credit_row}"

    # Verify types: should be TEXT, not REAL/FLOAT
    assert "REAL" not in debit_row[2] and "FLOAT" not in debit_row[2], "debit type should be TEXT"
    assert "REAL" not in credit_row[2] and "FLOAT" not in credit_row[2], "credit type should be TEXT"

    # Attempt to insert NULL debit: should fail
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit) "
            "VALUES (999, 1, '1101', 1, NULL, '0')"
        )
        conn.commit()

    # Attempt to insert NULL credit: should fail
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO journalline (id, entry_id, account_code, account_id, debit, credit) "
            "VALUES (998, 1, '1101', 1, '0', NULL)"
        )
        conn.commit()

    conn.close()


def test_migrated_asset_value_is_not_nullable(tmp_path):
    """
    P1D.2B: After migration, Asset value is NOT NULL in schema.

    Validates physical constraint prevents future NULL insertion.
    """
    db_file = tmp_path / "asset_not_null.db"

    # Create legacy Asset with valid REAL value
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE asset (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            value REAL,
            created_at DATETIME
        )
    """)
    conn.execute("INSERT INTO asset (id, name, value) VALUES (1, 'Asset A', 0.1)")
    conn.commit()
    conn.close()

    # Migrate
    migrate_database(str(db_file))

    # Verify schema: value is NOT NULL
    conn = sqlite3.connect(str(db_file))
    table_info = conn.execute("PRAGMA table_info(asset)").fetchall()
    schema_dict = {row[1]: row for row in table_info}

    value_row = schema_dict.get("value")

    assert value_row is not None, "value column exists"
    assert value_row[3] == 1, f"value should be NOT NULL, got: {value_row}"
    assert "REAL" not in value_row[2] and "FLOAT" not in value_row[2], "value type should be TEXT"

    # Attempt to insert NULL value: should fail
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO asset (id, name, value) VALUES (999, 'Invalid', NULL)"
        )
        conn.commit()

    conn.close()
