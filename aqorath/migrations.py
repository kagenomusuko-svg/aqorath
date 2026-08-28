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

CURRENT_SCHEMA_VERSION = 4
"""Current schema version. Additive 5AK metadata does not reinterpret v4 truth."""

# ============================================================
# Migration Registry
# ============================================================
def _create_current_schema(db_path):
    """Create complete current schema using models after structural migrations."""
    from aqorath import models as _models  # noqa: F401 - populate metadata
    from sqlmodel import SQLModel
    from sqlalchemy import create_engine

    db_path = Path(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        SQLModel.metadata.create_all(engine)
    finally:
        engine.dispose()


def _ensure_additive_current_schema(db_path):
    """Ensure additive tables belonging to frozen v4 without bumping user_version."""
    from aqorath import models as _models
    from sqlalchemy import create_engine

    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    finally:
        conn.close()

    if "fiscalpostingauditrecord" not in tables:
        raise RuntimeError(
            "Current v4 database is missing fiscalpostingauditrecord; refusing additive repair"
        )

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        _models.FiscalPostingAuditEffectRecord.__table__.create(
            engine,
            checkfirst=True,
        )
        _models.EntityRecord.__table__.create(engine, checkfirst=True)
        _models.ProgramRecord.__table__.create(engine, checkfirst=True)
        _models.FixedAssetRecord.__table__.create(engine, checkfirst=True)
        _models.FixedAssetDepreciationPostingRecord.__table__.create(
            engine,
            checkfirst=True,
        )
        _models.FixedAssetAcquisitionPostingRecord.__table__.create(
            engine,
            checkfirst=True,
        )
        _models.EntityProfileRecord.__table__.create(engine, checkfirst=True)
        _models.FiscalProfileRecord.__table__.create(engine, checkfirst=True)
        _models.ThirdPartyRecord.__table__.create(engine, checkfirst=True)
        _models.DocumentReferenceRecord.__table__.create(engine, checkfirst=True)
        _models.CfdiImportMetadataRecord.__table__.create(engine, checkfirst=True)
        _models.AnalyticalDimensionRecord.__table__.create(engine, checkfirst=True)
        _models.AnalyticalDimensionValueRecord.__table__.create(engine, checkfirst=True)
        _models.JournalLineAnalyticalDimensionRecord.__table__.create(
            engine,
            checkfirst=True,
        )
        _models.UserKnowledgeStateRecord.__table__.create(engine, checkfirst=True)
    finally:
        engine.dispose()


def _migrate_0_to_1(db_path):
    """Migrate unversioned storage to exact-money/governed-account foundation."""
    db_path = Path(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}
        is_empty = len(existing_tables) == 0
    finally:
        conn.close()

    if is_empty:
        _create_current_schema(str(db_path))
        return

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN IMMEDIATE")
        if "account" in existing_tables:
            _migrate_account_legacy(conn)
        if "journalline" in existing_tables:
            _migrate_journalline_legacy(conn)
        if "asset" in existing_tables:
            _migrate_asset_legacy(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    _create_current_schema(str(db_path))


def _migrate_account_legacy(conn):
    """Add governed-extension columns to a legacy Account table."""
    cursor = conn.execute("PRAGMA table_info(account)")
    columns = {row[1] for row in cursor.fetchall()}

    if "origin" not in columns:
        conn.execute(
            "ALTER TABLE account ADD COLUMN origin VARCHAR NOT NULL DEFAULT 'canonical'"
        )
    else:
        conn.execute(
            "UPDATE account SET origin = 'canonical' "
            "WHERE origin IS NULL OR TRIM(origin) = ''"
        )

    if "parent_id" not in columns:
        conn.execute("ALTER TABLE account ADD COLUMN parent_id INTEGER NULL")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_account_parent_id ON account(parent_id)"
    )


def _migrate_journalline_legacy(conn):
    """Convert JournalLine debit/credit REAL/FLOAT columns to exact TEXT."""
    cursor = conn.execute("PRAGMA table_info(journalline)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    debit_type = columns.get("debit", "").upper()
    credit_type = columns.get("credit", "").upper()
    if (
        "REAL" not in debit_type
        and "FLOAT" not in debit_type
        and "REAL" not in credit_type
        and "FLOAT" not in credit_type
    ):
        return

    required = {
        "id",
        "entry_id",
        "account_code",
        "account_id",
        "debit",
        "credit",
        "description",
        "created_at",
    }
    if not required.issubset(columns.keys()):
        missing = required - set(columns.keys())
        raise RuntimeError(
            f"Cannot migrate journalline: missing required columns {missing}"
        )

    unknown = set(columns.keys()) - required
    if unknown:
        raise RuntimeError(
            f"Cannot migrate journalline: unknown columns {unknown} would be lost. "
            f"Please add explicit migration logic for these columns."
        )

    conn.execute(
        """
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
        """
    )

    cursor = conn.execute(
        "SELECT id, entry_id, account_code, account_id, debit, credit, description, created_at "
        "FROM journalline"
    )
    for row in cursor:
        (
            line_id,
            entry_id,
            account_code,
            account_id,
            debit,
            credit,
            description,
            created_at,
        ) = row
        if debit is None or credit is None:
            raise RuntimeError(
                f"Cannot migrate journalline id={line_id}: NULL monetary value found. "
                f"debit={debit}, credit={credit}. This represents inconsistent state."
            )
        debit_str = str(to_decimal_exact(Decimal(str(debit))))
        credit_str = str(to_decimal_exact(Decimal(str(credit))))
        conn.execute(
            "INSERT INTO journalline__aqorath_v1 "
            "(id, entry_id, account_code, account_id, debit, credit, description, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                line_id,
                entry_id,
                account_code,
                account_id,
                debit_str,
                credit_str,
                description,
                created_at,
            ),
        )

    conn.execute("DROP TABLE journalline")
    conn.execute("ALTER TABLE journalline__aqorath_v1 RENAME TO journalline")


def _migrate_asset_legacy(conn):
    """Convert Asset.value REAL/FLOAT to exact TEXT while preserving identity."""
    cursor = conn.execute("PRAGMA table_info(asset)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    value_type = columns.get("value", "").upper()

    if "value" not in columns or (
        "REAL" not in value_type and "FLOAT" not in value_type
    ):
        return

    required = {"id", "name", "value", "created_at"}
    if not required.issubset(columns.keys()):
        missing = required - set(columns.keys())
        raise RuntimeError(
            f"Cannot migrate asset: missing required columns {missing}"
        )

    unknown = set(columns.keys()) - required
    if unknown:
        raise RuntimeError(
            f"Cannot migrate asset: unknown columns {unknown} would be lost. "
            f"Please add explicit migration logic for these columns."
        )

    conn.execute(
        """
        CREATE TABLE asset__aqorath_v1 (
            id INTEGER PRIMARY KEY,
            name VARCHAR,
            value TEXT NOT NULL,
            created_at DATETIME
        )
        """
    )
    cursor = conn.execute("SELECT id, name, value, created_at FROM asset")
    for row in cursor:
        asset_id, name, value, created_at = row
        if value is None:
            raise RuntimeError(
                f"Cannot migrate asset id={asset_id}: NULL value found. "
                f"This represents inconsistent state."
            )
        value_str = str(to_decimal_exact(Decimal(str(value))))
        conn.execute(
            "INSERT INTO asset__aqorath_v1 (id, name, value, created_at) "
            "VALUES (?, ?, ?, ?)",
            (asset_id, name, value_str, created_at),
        )

    conn.execute("DROP TABLE asset")
    conn.execute("ALTER TABLE asset__aqorath_v1 RENAME TO asset")


def _migrate_1_to_2(db_path):
    """Add persistent role -> Account identity bindings without duplicating account_code."""
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accountrolebinding (
                id INTEGER PRIMARY KEY,
                role VARCHAR NOT NULL UNIQUE,
                account_id INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(account_id) REFERENCES account(id)
            )
            """
        )
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


def _migrate_2_to_3(db_path):
    """Add exact effective-dated fiscal rule versions as SQLite authority."""
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fiscalruleversion (
                id INTEGER PRIMARY KEY,
                rule_key VARCHAR NOT NULL,
                jurisdiction VARCHAR NOT NULL,
                regime VARCHAR NOT NULL,
                entity_type VARCHAR NOT NULL,
                effective_from DATE NOT NULL,
                effective_to DATE,
                value TEXT NOT NULL,
                unit VARCHAR NOT NULL,
                source_ref VARCHAR NOT NULL,
                created_at DATETIME NOT NULL,
                CONSTRAINT uq_fiscal_rule_scope_start UNIQUE (
                    rule_key, jurisdiction, regime, entity_type, effective_from
                )
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_fiscalruleversion_lookup "
            "ON fiscalruleversion(rule_key, jurisdiction, regime, entity_type, effective_from, effective_to)"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_3_to_4(db_path):
    """Add one-to-one fiscal posting audit metadata linked to JournalEntry."""
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fiscalpostingauditrecord (
                id INTEGER PRIMARY KEY,
                entry_id INTEGER NOT NULL UNIQUE,
                fact_type VARCHAR NOT NULL,
                fact_amount TEXT NOT NULL,
                payment_method VARCHAR NOT NULL,
                effective_date DATE NOT NULL,
                jurisdiction VARCHAR NOT NULL,
                regime VARCHAR NOT NULL,
                entity_type VARCHAR NOT NULL,
                rule_key VARCHAR NOT NULL,
                base TEXT NOT NULL,
                rate TEXT NOT NULL,
                unit VARCHAR NOT NULL,
                rule_effective_from DATE NOT NULL,
                rule_effective_to DATE,
                rule_source_ref VARCHAR NOT NULL,
                exact_fiscal_amount TEXT NOT NULL,
                rounding_policy_key VARCHAR NOT NULL,
                rounding_quantizer TEXT NOT NULL,
                rounding_mode VARCHAR NOT NULL,
                rounding_source_ref VARCHAR NOT NULL,
                rounded_fiscal_amount TEXT NOT NULL,
                amount_basis VARCHAR NOT NULL,
                adjustment_role VARCHAR NOT NULL,
                fiscal_role VARCHAR NOT NULL,
                fiscal_side VARCHAR NOT NULL,
                zero_fiscal_line_policy VARCHAR NOT NULL,
                omitted_zero_account_role VARCHAR,
                omitted_zero_account_id INTEGER,
                omitted_zero_account_code VARCHAR,
                omitted_zero_account_name VARCHAR,
                omitted_zero_side VARCHAR,
                omitted_zero_amount TEXT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(entry_id) REFERENCES journalentry(id)
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_fiscalpostingauditrecord_entry_id "
            "ON fiscalpostingauditrecord(entry_id)"
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
    3: _migrate_2_to_3,
    4: _migrate_3_to_4,
}
"""Registry of migration callables. Key: target version."""


# ============================================================
# Public API
# ============================================================
def get_schema_version(db_path) -> int:
    """Return PRAGMA user_version, treating missing/unversioned DB as zero."""
    db_path = Path(db_path)
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute("PRAGMA user_version")
            return int(cursor.fetchone()[0])
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        raise RuntimeError(f"Cannot read schema version from {db_path}: {e}")


def _set_schema_version(db_path, version: int) -> None:
    """Set PRAGMA user_version only after a successful migration step."""
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
    """Return whether SQLite PRAGMA integrity_check reports ``ok``."""
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
    except Exception:
        return False


def create_database_backup(db_path, backup_dir=None) -> dict:
    """Create and validate a SQLite-consistent pre-migration backup."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise RuntimeError(f"Database {db_path} does not exist")
    if not validate_sqlite_integrity(str(db_path)):
        raise RuntimeError(f"Database {db_path} is corrupt or not valid SQLite")

    if backup_dir is None:
        backup_dir = db_path.parent / ".aqorath_backups"
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat()[:19].replace(":", "-")
    unique_id = str(uuid4())[:8]
    backup_name = f"{db_path.stem}.backup.{timestamp}.{unique_id}.db"
    backup_path = backup_dir / backup_name

    try:
        source_conn = sqlite3.connect(str(db_path))
        backup_conn = sqlite3.connect(str(backup_path))
        try:
            source_conn.backup(backup_conn)
        finally:
            backup_conn.close()
            source_conn.close()
    except Exception as e:
        if backup_path.exists():
            try:
                backup_path.unlink()
            except Exception:
                pass
        raise RuntimeError(f"Failed to create backup: {e}")

    if not validate_sqlite_integrity(str(backup_path)):
        backup_path.unlink()
        raise RuntimeError("Created backup is corrupt")
    return {"backup_path": str(backup_path)}


def restore_database_backup(backup_path, target_path) -> None:
    """Atomically restore target from a validated SQLite backup."""
    backup_path = Path(backup_path)
    target_path = Path(target_path)
    if not backup_path.exists():
        raise RuntimeError(f"Backup {backup_path} does not exist")
    if not validate_sqlite_integrity(str(backup_path)):
        raise RuntimeError(f"Backup {backup_path} is corrupt or not valid SQLite")

    temp_path = target_path.parent / f"{target_path.name}.restore.{uuid4()}"
    try:
        backup_conn = sqlite3.connect(str(backup_path))
        temp_conn = sqlite3.connect(str(temp_path))
        try:
            backup_conn.backup(temp_conn)
        finally:
            temp_conn.close()
            backup_conn.close()
        if not validate_sqlite_integrity(str(temp_path)):
            raise RuntimeError("Restored database is corrupt")
        os.replace(str(temp_path), str(target_path))
    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise


def migrate_database(db_path) -> dict:
    """Migrate one SQLite database sequentially and ensure additive v4 metadata."""
    db_path = Path(db_path)
    current_version = get_schema_version(str(db_path))

    if current_version > CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version {current_version} is newer than "
            f"application CURRENT_SCHEMA_VERSION {CURRENT_SCHEMA_VERSION}. "
            f"Refusing downgrade."
        )

    if current_version == CURRENT_SCHEMA_VERSION:
        if db_path.exists() and not validate_sqlite_integrity(str(db_path)):
            raise RuntimeError(f"Database {db_path} is corrupt")
        _ensure_additive_current_schema(str(db_path))
        return {
            "from_version": current_version,
            "to_version": current_version,
            "migrated": False,
            "backup_path": None,
        }

    backup_path = None
    if db_path.exists():
        if not validate_sqlite_integrity(str(db_path)):
            raise RuntimeError(f"Database {db_path} is corrupt and cannot be migrated")
        backup_result = create_database_backup(str(db_path))
        backup_path = backup_result["backup_path"]

    for target_version in range(current_version + 1, CURRENT_SCHEMA_VERSION + 1):
        if target_version not in MIGRATIONS:
            raise RuntimeError(
                f"No migration registered for schema version {target_version}"
            )
        migration_callable = MIGRATIONS[target_version]
        migration_callable(str(db_path))
        _set_schema_version(str(db_path), target_version)
        if not validate_sqlite_integrity(str(db_path)):
            raise RuntimeError(
                f"Database is corrupt after migration to version {target_version}"
            )

    _ensure_additive_current_schema(str(db_path))
    return {
        "from_version": current_version,
        "to_version": CURRENT_SCHEMA_VERSION,
        "migrated": current_version < CURRENT_SCHEMA_VERSION,
        "backup_path": backup_path,
    }
