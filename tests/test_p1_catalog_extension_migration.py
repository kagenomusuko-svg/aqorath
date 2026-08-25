"""
P1-3 Migration tests: verify that legacy DB schema is upgraded.

Schema evolution: Account pre-1C.3B → post-1C.3B
- Add origin column (default "canonical")
- Add parent_id column (NULL, FK account.id)
- Preserve all existing data
"""

import pytest
import sqlite3
from pathlib import Path
from sqlalchemy import inspect
from sqlmodel import Session
import aqorath.storage as storage
from aqorath.models import Account


def test_existing_account_table_is_upgraded_for_extensions(tmp_path, monkeypatch):
    """
    P1-3: Legacy DB with pre-1C.3B account table is deterministically upgraded.
    
    SETUP: Create SQLite with schema BEFORE P1-3 (no origin/parent_id)
    CREATE TABLE account (
        id INTEGER PRIMARY KEY,
        code VARCHAR UNIQUE,
        name VARCHAR NOT NULL,
        nature VARCHAR NOT NULL,
        vat_flag BOOLEAN NOT NULL DEFAULT 0,
        created_at DATETIME
    )
    
    INSERT: 1101 / Bancos / Deudora
    
    ACTION: Execute production init_db() pathway
    
    VERIFICATION:
    - origin column exists
    - parent_id column exists
    - 1101 data preserved (code, name, nature)
    - 1101.origin == "canonical"
    - 1101.parent_id is None
    """
    db_file = tmp_path / "legacy_test.db"
    
    # Create pre-1C.3B schema manually
    conn = sqlite3.connect(str(db_file))
    try:
        conn.execute("""
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                code VARCHAR UNIQUE,
                name VARCHAR NOT NULL,
                nature VARCHAR NOT NULL,
                vat_flag BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME
            )
        """)
        
        # Insert canonical account
        conn.execute(
            "INSERT INTO account (code, name, nature, vat_flag) VALUES (?, ?, ?, ?)",
            ("1101", "Bancos", "Deudora", False)
        )
        
        conn.commit()
    finally:
        conn.close()
    
    # Set env to use legacy DB
    monkeypatch.setenv("AQORATH_DB", str(db_file))
    
    # Execute production pathway: this should migrate the schema
    engine = storage.init_db(str(db_file), create_tables=True)
    
    # Verify schema upgraded
    insp = inspect(engine)
    columns = {c["name"] for c in insp.get_columns("account")}
    
    assert "origin" in columns, "origin column must exist after migration"
    assert "parent_id" in columns, "parent_id column must exist after migration"
    
    # Verify data preserved
    with Session(engine) as session:
        account_1101 = session.query(Account).filter(Account.code == "1101").one_or_none()
        
        assert account_1101 is not None, "1101 must exist after migration"
        assert account_1101.code == "1101", "code must be preserved"
        assert account_1101.name == "Bancos", "name must be preserved"
        assert account_1101.nature == "Deudora", "nature must be preserved"
        assert account_1101.origin == "canonical", "origin must default to canonical"
        assert account_1101.parent_id is None, "parent_id must be None for canonical"


def test_migration_is_idempotent(tmp_path, monkeypatch):
    """
    P1-3: Running migration multiple times should be safe.
    
    Create legacy DB, run init_db() twice, verify no errors and data intact.
    """
    db_file = tmp_path / "idempotent_test.db"
    
    # Create legacy schema
    conn = sqlite3.connect(str(db_file))
    try:
        conn.execute("""
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                code VARCHAR UNIQUE,
                name VARCHAR NOT NULL,
                nature VARCHAR NOT NULL,
                vat_flag BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME
            )
        """)
        conn.execute(
            "INSERT INTO account (code, name, nature) VALUES (?, ?, ?)",
            ("1101", "Bancos", "Deudora")
        )
        conn.execute(
            "INSERT INTO account (code, name, nature) VALUES (?, ?, ?)",
            ("4101", "Ventas", "Acreedora")
        )
        conn.commit()
    finally:
        conn.close()
    
    monkeypatch.setenv("AQORATH_DB", str(db_file))
    
    # First init_db
    engine1 = storage.init_db(str(db_file), create_tables=True)
    
    with Session(engine1) as session:
        count_before = session.query(Account).count()
    
    # Second init_db (should be idempotent)
    engine2 = storage.init_db(str(db_file), create_tables=True)
    
    with Session(engine2) as session:
        count_after = session.query(Account).count()
        accounts = session.query(Account).all()
        
        assert count_after == count_before, "Account count must not change"
        assert count_after == 2, "Should still have 1101 and 4101"
        
        for acc in accounts:
            assert acc.origin == "canonical", f"{acc.code} must have origin=canonical"
            assert acc.parent_id is None, f"{acc.code} must have parent_id=None"
