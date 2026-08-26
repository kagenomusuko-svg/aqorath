"""
P1D.2: Central database migration, backup, restore, and integrity authority.

This module serves as the single source of truth for SQLite schema evolution.
Responsibilities:
  - Version control via PRAGMA user_version
  - Sequential migrations (0 → 1 → 2 → ...)
  - Pre-migration backup
  - Integrity validation
  - Safe restore
  - Future schema rejection
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from decimal import Decimal

from aqorath.money import to_decimal_exact

# ============================================================
# Version Control
# ============================================================

CURRENT_SCHEMA_VERSION = 2
"""Current schema version. Incremented for each breaking change."""

# ============================================================
# Migration Registry
# ============================================================

def _create_current_schema(db_path):
    """
    Create complete current schema using models.

    MUST be called AFTER structural migrations.
    Imports models explicitly to ensure metadata is populated.
    """
    from aqorath import models as _models  # Explicit import
    from sqlmodel import SQLModel
    from sqlalchemy import create_engine

    db_path = Path(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        SQLModel.metadata.create_all(engine)
    finally:
        engine.dispose()


def _migrate_0_to_1(db_path):
    """
    Migrate from unversioned (0) to version 1.

    Handles:
    - Create schema if DB is empty
    - Account: add origin/parent_id, backfill
    - JournalLine: migrate REAL/FLOAT → TEXT for debit/credit
    - Asset: migrate value REAL/FLOAT → TEXT
    - All structural changes in ONE transaction
    - Create remaining tables if missing
    """
    db_path = Path(db_path)

    # Determine if DB is empty
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}
        is_empty = len(existing_tables) == 0
    finally:
        conn.close()

    # If empty: create full schema and return
    if is_empty:
        _create_current_schema(str(db_path))
        return

    # DB exists: perform migrations in single transaction
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Account migration
        if "account" in existing_tables:
            _migrate_account_legacy(conn)

        # JournalLine migration
        if "journalline" in existing_tables:
            _migrate_journalline_legacy(conn)

        # Asset migration
        if "asset" in existing_tables:
            _migrate_asset_legacy(conn)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Create any missing tables
    _create_current_schema(str(db_path))


def _migrate_account_legacy(conn):
    """
    Add origin and parent_id columns to account if missing.
    Backfill existing accounts with canonical defaults.
    """
    cursor = conn.execute("PRAGMA table_info(account)")
    columns = {row[1] for row in cursor.fetchall()}

    # Add origin if missing
    if "origin" not in columns:
        conn.execute("ALTER TABLE account ADD COLUMN origin VARCHAR NOT NULL DEFAULT 'canonical'")
    else:
        # Backfill NULL/empty origin to canonical
        conn.execute(
            "UPDATE account SET origin = 'canonical' WHERE origin IS NULL OR TRIM(origin) = ''"
        )

    # Add parent_id if missing
    if "parent_id" not in columns:
        conn.execute("ALTER TABLE account ADD COLUMN parent_id INTEGER NULL")

    # Create index (IF NOT EXISTS handles idempotency, errors must propagate)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_account_parent_id ON account(parent_id)")


def _migrate_journalline_legacy(conn):
    """
    Convert JournalLine debit/credit from REAL/FLOAT to TEXT.
    Preserves row identity and metadata.

    CRITICAL: Called within _migrate_0_to_1's transaction.
    Do NOT begin/commit transactions here.
    """
    cursor = conn.execute("PRAGMA table_info(journalline)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    debit_type = columns.get("debit", "").upper()
    credit_type = columns.get("credit", "").upper()

    # If already TEXT: nothing to do
    if "REAL" not in debit_type and "FLOAT" not in debit_type and \
       "REAL" not in credit_type and "FLOAT" not in credit_type:
        return

    # Check for required columns
    required = {"id", "entry_id", "account_code", "account_id", "debit", "credit",
                "description", "created_at"}
    if not required.issubset(columns.keys()):
        missing = required - set(columns.keys())
        raise RuntimeError(
            f"Cannot migrate journalline: missing required columns {missing}"
        )

    # Check for unpreserved columns (not migrating silently)
    known_columns = required  # ONLY these columns are supported
    unknown = set(columns.keys()) - known_columns
    if unknown:
        raise RuntimeError(
            f"Cannot migrate journalline: unknown columns {unknown} would be lost. "
            f"Please add explicit migration logic for these columns."
        )

    # Rebuild journalline with TEXT money columns (NOT NULL)
    # Create temporary table with TEXT money columns
    conn.execute("""
        CREATE TABLE journalline__aqorath_v1 (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER,
            account_code VARCHAR,
            account_id INTEGER,
            debit TEXT NOT NULL,
            credit TEXT NOT NULL,
            description VARCHAR,
            created_at DATETIME
        )
    """)

    # Copy and convert data
    cursor = conn.execute(
        "SELECT id, entry_id, account_code, account_id, debit, credit, description, created_at "
        "FROM journalline"
    )

    for row in cursor:
        line_id, entry_id, account_code, account_id, debit, credit, description, created_at = row

        # Reject NULL monetary values
        if debit is None or credit is None:
            raise RuntimeError(
                f"Cannot migrate journalline id={line_id}: NULL monetary value found. "
                f"debit={debit}, credit={credit}. This represents inconsistent state."
            )

        # Convert money with exact precision
        debit_str = str(to_decimal_exact(Decimal(str(debit))))
        credit_str = str(to_decimal_exact(Decimal(str(credit))))

        conn.execute(
            "INSERT INTO journalline__aqorath_v1 "
            "(id, entry_id, account_code, account_id, debit, credit, description, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (line_id, entry_id, account_code, account_id, debit_str, credit_str, description, created_at)
        )

    # Drop old table and rename
    conn.execute("DROP TABLE journalline")
    conn.execute("ALTER TABLE journalline__aqorath_v1 RENAME TO journalline")


def _migrate_asset_legacy(conn):
    """
    Convert Asset.value from REAL/FLOAT to TEXT.
    Preserves row identity and metadata.

    CRITICAL: Called within _migrate_0_to_1's transaction.
    Do NOT begin/commit transactions here.
    """
    cursor = conn.execute("PRAGMA table_info(asset)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    value_type = columns.get("value", "").upper()

    # If already TEXT or doesn't exist: nothing to do
    if "value" not in columns or ("REAL" not in value_type and "FLOAT" not in value_type):
        return

    # Check for required columns
    required = {"id", "name", "value", "created_at"}
    if not required.issubset(columns.keys()):
        missing = required - set(columns.keys())
        raise RuntimeError(
            f"Cannot migrate asset: missing required columns {missing}"
        )

    # Check for unpreserved columns
    known_columns = required  # ONLY these columns are supported
    unknown = set(columns.keys()) - known_columns
    if unknown:
        raise RuntimeError(
            f"Cannot migrate asset: unknown columns {unknown} would be lost. "
            f"Please add explicit migration logic for these columns."
        )

    # Rebuild asset with TEXT value column (NOT NULL)
    conn.execute("""
        CREATE TABLE asset__aqorath_v1 (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            value TEXT NOT NULL,
            created_at DATETIME
        )
    """)

    cursor = conn.execute(
        "SELECT id, name, value, created_at FROM asset"
    )

    for row in cursor:
        asset_id, name, value, created_at = row

        # Reject NULL value
        if value is None:
            raise RuntimeError(
                f"Cannot migrate asset id={asset_id}: NULL value found. "
                f"This represents inconsistent state."
            )

        value_str = str(to_decimal_exact(Decimal(str(value))))

        conn.execute(
            "INSERT INTO asset__aqorath_v1 (id, name, value, created_at) VALUES (?, ?, ?, ?)",
            (asset_id, name, value_str, created_at)
        )

    conn.execute("DROP TABLE asset")
    conn.execute("ALTER TABLE asset__aqorath_v1 RENAME TO asset")


def _migrate_1_to_2(db_path):
    """Add persistent role -> Account identity bindings without duplicating account_code."""
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accountrolebinding (
                id INTEGER PRIMARY KEY,
                role VARCHAR NOT NULL UNIQUE,
                account_id INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(account_id) REFERENCES account(id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_accountrolebinding_account_id "
            "ON accountrolebinding(account_id)"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


MIGRATIONS = {
    1: _migrate_0_to_1,
    2: _migrate_1_to_2,
}
"""Registry of migration callables. Key: target version."""


# ============================================================
# Public API
# ============================================================

def get_schema_version(db_path) -> int:
    """
    Get current schema version from PRAGMA user_version.

    If DB doesn't exist: return 0 (unversioned).
    If DB exists but has no version: return 0.
    """
    db_path = Path(db_path)

    if not db_path.exists():
        return 0

    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA user_version")
            version = cursor.fetchone()[0]
            return int(version)
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        raise RuntimeError(f"Cannot read schema version from {db_path}: {e}")


def _set_schema_version(db_path, version: int) -> None:
    """
    Set PRAGMA user_version to target version.
    Only call after successful migration.
    """
    if not isinstance(version, int) or version < 0:
        raise ValueError(f"Schema version must be non-negative int, got {version}")

    db_path = Path(db_path)

    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        raise RuntimeError(f"Cannot set schema version on {db_path}: {e}")


def validate_sqlite_integrity(db_path) -> bool:
    """
    Validate SQLite database integrity.

    Returns:
      True if PRAGMA integrity_check returns "ok"
      False if DB is corrupt, doesn't exist, or is not SQLite
    """
    db_path = Path(db_path)

    if not db_path.exists():
        return False

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cursor = conn.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            return result == "ok"
        finally:
            conn.close()
    except (sqlite3.DatabaseError, Exception):
        return False


def create_database_backup(db_path, backup_dir=None) -> dict:
    """
    Create pre-migration backup of database.

    Validates source before backing up.
    Uses SQLite backup API for consistency.

    Returns:
      {"backup_path": str(path), ...}
    """
    db_path = Path(db_path)

    # Validate source
    if not db_path.exists():
        raise RuntimeError(f"Database {db_path} does not exist")

    if not validate_sqlite_integrity(str(db_path)):
        raise RuntimeError(f"Database {db_path} is corrupt or not valid SQLite")

    # Determine backup directory
    if backup_dir is None:
        backup_dir = db_path.parent / ".aqorath_backups"

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique backup name
    timestamp = datetime.now().isoformat()[:19].replace(":", "-")
    unique_id = str(uuid4())[:8]
    backup_name = f"{db_path.stem}.backup.{timestamp}.{unique_id}.db"
    backup_path = backup_dir / backup_name

    # Perform backup using SQLite API
    try:
        source_conn = sqlite3.connect(str(db_path))
        backup_conn = sqlite3.connect(str(backup_path))

        try:
            source_conn.backup(backup_conn)
        finally:
            backup_conn.close()
            source_conn.close()
    except Exception as e:
        # Clean up defective backup if it was created
        if backup_path.exists():
            try:
                backup_path.unlink()
            except Exception:
                pass
        raise RuntimeError(f"Failed to create backup: {e}")

    # Validate backup
    if not validate_sqlite_integrity(str(backup_path)):
        backup_path.unlink()
        raise RuntimeError("Created backup is corrupt")

    return {"backup_path": str(backup_path)}


def restore_database_backup(backup_path, target_path) -> None:
    """
    Restore target database from backup.

    Validates backup first. Creates temporary file in same filesystem.
    Only replaces target after successful validation of restored copy.
    """
    backup_path = Path(backup_path)
    target_path = Path(target_path)

    # Validate backup
    if not backup_path.exists():
        raise RuntimeError(f"Backup {backup_path} does not exist")

    if not validate_sqlite_integrity(str(backup_path)):
        raise RuntimeError(f"Backup {backup_path} is corrupt or not valid SQLite")

    # Create temporary restore in same filesystem as target
    temp_path = target_path.parent / f"{target_path.name}.restore.{uuid4()}"

    try:
        # Restore to temporary location
        backup_conn = sqlite3.connect(str(backup_path))
        temp_conn = sqlite3.connect(str(temp_path))

        try:
            backup_conn.backup(temp_conn)
        finally:
            temp_conn.close()
            backup_conn.close()

        # Validate restored copy
        if not validate_sqlite_integrity(str(temp_path)):
            raise RuntimeError("Restored database is corrupt")

        # Atomic replace
        os.replace(str(temp_path), str(target_path))

    except Exception:
        # Clean up temp file if it exists
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise


def migrate_database(db_path) -> dict:
    """
    Migrate database to current schema version.

    Handles:
    - Nonexistent DB (creates at CURRENT_SCHEMA_VERSION)
    - Unversioned legacy DB (migrates 0 → CURRENT)
    - Current DB (no-op, validates integrity)
    - Future DB (rejects, leaves unchanged)
    - Corrupt DB (rejects)

    Returns:
      {
        "from_version": int,
        "to_version": int,
        "migrated": bool,
        "backup_path": str | None,
      }
    """
    db_path = Path(db_path)

    # Get current version
    current_version = get_schema_version(str(db_path))

    # Check for future schema
    if current_version > CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is newer than "
            f"application CURRENT_SCHEMA_VERSION {CURRENT_SCHEMA_VERSION}. "
            f"Refusing downgrade."
        )

    # No-op: already current
    if current_version == CURRENT_SCHEMA_VERSION:
        if db_path.exists():
            if not validate_sqlite_integrity(str(db_path)):
                raise RuntimeError(f"Database {db_path} is corrupt")
        return {
            "from_version": current_version,
            "to_version": current_version,
            "migrated": False,
            "backup_path": None,
        }

    # DB needs migration or is new
    backup_path = None

    if db_path.exists():
        # Existing DB: validate and backup before migrating
        if not validate_sqlite_integrity(str(db_path)):
            raise RuntimeError(f"Database {db_path} is corrupt and cannot be migrated")

        backup_result = create_database_backup(str(db_path))
        backup_path = backup_result["backup_path"]

    # Execute migration sequence
    for target_version in range(current_version + 1, CURRENT_SCHEMA_VERSION + 1):
        if target_version not in MIGRATIONS:
            raise RuntimeError(
                f"No migration registered for schema version {target_version}"
            )

        migration_callable = MIGRATIONS[target_version]

        try:
            migration_callable(str(db_path))
        except Exception:
            # Migration failed: don't advance version, leave backup intact
            raise

        # Only advance version after successful migration
        _set_schema_version(str(db_path), target_version)

        # Validate after each step
        if not validate_sqlite_integrity(str(db_path)):
            raise RuntimeError(
                f"Database is corrupt after migration to version {target_version}"
            )

    return {
        "from_version": current_version,
        "to_version": CURRENT_SCHEMA_VERSION,
        "migrated": current_version < CURRENT_SCHEMA_VERSION,
        "backup_path": backup_path,
    }